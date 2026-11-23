"""Leitura de valores armazenados de XLSX, sem executar fórmulas.

Fórmulas são aceitas apenas se o arquivo contiver resultado em cache; erros de
fórmula nos blocos utilizados interrompem o processamento.
"""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CELL = re.compile(r"^([A-Z]{1,3})(\d{1,7})$")

@dataclass
class ExcelContent:
    sheets: dict[str, dict[str, object]]
    formula_errors: list[dict]
    formulas_without_cache: list[dict]
    def cell(self, sheet: str, address: str):
        for name, values in self.sheets.items():
            if name.strip().casefold() == sheet.strip().casefold():
                return values.get(address.upper())
        raise KeyError(f"Aba não encontrada: {sheet}")
    def has_sheet(self, sheet: str) -> bool:
        return any(k.strip().casefold() == sheet.strip().casefold() for k in self.sheets)


def _texts(node):
    return "".join((n.text or "") for n in node.iter(f"{{{MAIN}}}t"))


def read_excel(source: bytes, max_uncompressed: int = 25_000_000) -> ExcelContent:
    if len(source) > 15_000_000:
        raise ValueError("A planilha ultrapassa o limite de 15 MB.")
    try:
        z = ZipFile(BytesIO(source))
    except BadZipFile as e:
        raise ValueError("Arquivo não é um XLSX válido.") from e
    with z:
        if sum(i.file_size for i in z.infolist()) > max_uncompressed:
            raise ValueError("Conteúdo XLSX descompactado excede o limite autorizado.")
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        relroot = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relationships = {node.attrib["Id"]: node.attrib["Target"] for node in relroot.findall(f"{{{PKG_REL}}}Relationship")}
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
            strings = [_texts(si) for si in tree.findall(f"{{{MAIN}}}si")]
        sheets = {}
        errors = []
        uncached = []
        for sh in wb.findall(f".//{{{MAIN}}}sheet"):
            name = sh.attrib["name"]
            rel_id = sh.attrib.get(f"{{{REL}}}id")
            if rel_id not in relationships:
                continue
            target = relationships[rel_id].replace("\\", "/").lstrip("/")
            path = target if target.startswith("xl/") else "xl/" + target
            if ".." in PurePosixPath(path).parts or path not in z.namelist():
                raise ValueError(f"Caminho interno XLSX inválido: {target}")
            tree = ET.fromstring(z.read(path))
            cells = {}
            for el in tree.findall(f".//{{{MAIN}}}sheetData/{{{MAIN}}}row/{{{MAIN}}}c"):
                addr = el.attrib.get("r", "").upper()
                if not CELL.fullmatch(addr):
                    continue
                val_node = el.find(f"{{{MAIN}}}v")
                formula = el.find(f"{{{MAIN}}}f")
                xtype = el.attrib.get("t")
                raw = None if val_node is None else val_node.text
                if xtype == "inlineStr":
                    value = _texts(el)
                elif xtype == "s":
                    try:
                        value = strings[int(raw)]
                    except (ValueError, TypeError, IndexError):
                        value = None
                elif xtype == "b":
                    value = raw == "1"
                elif xtype in ("str", "e"):
                    value = raw
                elif raw is not None:
                    try:
                        value = float(raw)
                    except (TypeError, ValueError):
                        value = raw
                else:
                    value = None
                if xtype == "e":
                    errors.append({"aba": name, "celula": addr, "erro": str(value)})
                if formula is not None and value is None:
                    uncached.append({"aba": name, "celula": addr, "formula": formula.text})
                if value is not None:
                    cells[addr] = value
            sheets[name] = cells
        return ExcelContent(sheets=sheets, formula_errors=errors, formulas_without_cache=uncached)
