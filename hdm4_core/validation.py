"""Plano de atualização com mapa explícito e validações conservadoras."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from math import isfinite
from typing import Any

RODOVIA = "Características das rodovias"
TRAFEGO = "Taxas de crescimento e VMD"
ECONOMIA = "Dados Econômicos"
CUSTOS = "Custos de Manutenção"
ORCAMENTO = "Orçamento"

# Mantemos DESLIGADOS parâmetros com divergência de unidade/semântica
# (largura, trincas, base/projeto, CBR, crescimento/atraído, orçamento).
SAFE_FIELDS = (
    ("LENGTH", "Extensão", 7, "km", 0.01, 300),
    ("ROUGHNESS", "IRI — condição BASE", 30, "m/km (a confirmar no HDM-4)", 0.2, 20),
    ("RAVEL_AREA", "Desagregação — BASE", 31, "%", 0, 100),
    ("PHOLE_NUM", "Panelas — BASE", 32, "n/km", 0, 100_000),
    ("EDGEBREAK", "Bordo quebrado — BASE", 33, "m²/km", 0, 100_000),
    ("RUT_DEPTH", "Afundamento — BASE", 34, "mm", 0, 100),
)
VEICULOS = ("VL", "ON", "VC1", "VC2")

@dataclass
class PlannedChange:
    secao: str
    campo: str
    nome: str
    origem: str
    valor: float
    unidade: str
    minimo: float
    maximo: float
    antes: Any = None
    chave: str = "SECT_ID"
    valor_chave: str = ""
    status: str = "pendente"
    def asdict(self):
        return asdict(self)


def _number(value, what: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"Valor ausente: {what}")
    try:
        result = float(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Esperado valor numérico em {what}: {value!r}") from e
    if not isfinite(result):
        raise ValueError(f"Valor não finito em {what}")
    return result


def _as_positive_int(value, what: str) -> int:
    n = _number(value, what)
    if not n.is_integer() or n < 0:
        raise ValueError(f"Valor inteiro positivo esperado em {what}: {n}")
    return int(n)


def build_validation(excel, sections=("S1", "S2"), fields=None) -> tuple[list[PlannedChange], list[str], dict]:
    errors = []
    warnings = []
    for sheet in (RODOVIA, TRAFEGO, ECONOMIA, CUSTOS, ORCAMENTO):
        if not excel.has_sheet(sheet):
            errors.append(f"Aba obrigatória ausente: {sheet}")
    if errors:
        return [], errors, {"alertas": [], "resumo": {}}

    if fields is None:
        fields = [f[0] for f in SAFE_FIELDS]
    changes = []
    for section in sections:
        if section not in ("S1", "S2"):
            errors.append(f"Seção não suportada no piloto: {section}")
            continue
        col = "C" if section == "S1" else "H"
        for field, label, row, unit, minimum, maximum in SAFE_FIELDS:
            if field not in fields:
                continue
            address = f"{col}{row}"
            try:
                value = _number(excel.cell(RODOVIA, address), f"{section} {address}")
                if not minimum <= value <= maximum:
                    raise ValueError(f"Fora da faixa permitida em {section} {address}: {value} ({minimum}–{maximum})")
                changes.append(PlannedChange(section, field, label, f"{RODOVIA.strip()}!{address}", value, unit, minimum, maximum))
            except ValueError as exc:
                errors.append(str(exc))
    summary = {}
    try:
        l1 = _number(excel.cell(RODOVIA,"C7"),"extensão S1")
        l2 = _number(excel.cell(RODOVIA,"H7"),"extensão S2")
        budget = _number(excel.cell(ORCAMENTO, "H1"),"quilometragem orçamentária")
        summary.update(extensao_modelo_km=l1+l2, extensao_orcamento_km=budget)
        if abs((l1+l2) - budget) > 0.001:
            warnings.append(f"Extensão modelada ({l1+l2:.2f} km) difere da base orçamentária ({budget:.2f} km). Não se recalcula orçamento automaticamente.")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        for section, start, row in (("S1",21,25),("S2",29,33)):
            vehicles = [_as_positive_int(excel.cell(TRAFEGO, f"I{r}"),f"{section} 2024 categoria linha {r}") for r in range(start,start+4)]
            total = _as_positive_int(excel.cell(TRAFEGO,f"I{row}"),f"{section} VMD total 2024")
            summary[f"vmd_{section}_2024"] = total
            if sum(vehicles)!=total:
                errors.append(f"VMD 2024 {section}: soma das categorias ({sum(vehicles)}) diferente do total ({total}).")
    except ValueError as exc:
        errors.append(str(exc))
    for row, vehicle in zip(range(5,9),VEICULOS):
        try:
            rate=_number(excel.cell(TRAFEGO,f"C{row}"),f"taxa {vehicle}")
            if not 0 <= rate <= 0.3:
                errors.append(f"Taxa de crescimento {vehicle}: {rate} fora de 0 a 30% a.a.")
            summary[f"crescimento_{vehicle}"]=rate
        except ValueError as exc:
            errors.append(str(exc))
    ignored = [e for e in excel.formula_errors if e["celula"] not in {c.origem.split('!')[-1] for c in changes}]
    if ignored:
        warnings.append(f"Planilha contém {len(ignored)} células com erros de fórmula fora dos campos aplicados; não serão utilizadas.")
    uncached = len(excel.formulas_without_cache)
    if uncached:
        warnings.append(f"Existem {uncached} fórmulas sem resultado em cache; verificar atualização no Excel.")
    warnings.append("Largura da pista, trincamento, CBR, tráfego, frota, custos, padrões e cronograma não serão alterados nesta versão. Dependem de mapeamento validado.")
    return changes, errors, {"alertas": warnings, "resumo": summary}


def attach_old_values(changes, sections: list[dict], key_name: str = "SECT_ID"):
    """Une dados por chave exata (sem associação por ordem dos registros)."""
    out=[]
    by_id = {str(row.get(key_name, "")).strip().casefold(): row for row in sections}
    for change in changes:
        row = by_id.get(change.secao.casefold())
        if row is None:
            raise ValueError(f"Não há correspondência inequívoca para seção {change.secao} em SECTIONS.{key_name}.")
        if change.campo not in row:
            raise ValueError(f"Campo inexistente na tabela SECTIONS: {change.campo}.")
        change.antes = row[change.campo]
        change.valor_chave = str(row[key_name])
        if change.antes is None:
            raise ValueError(f"Valor atual é nulo para {change.secao}.{change.campo}; revisão manual exigida.")
        old = _number(change.antes, f"valor original {change.secao}.{change.campo}")
        change.status = "sem alteração" if abs(old-change.valor) <= 1e-9 else "alterar"
        out.append(change)
    return out
