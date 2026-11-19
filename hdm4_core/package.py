"""Pacote de importação: intencionalmente NÃO afirma ser workspace HDM4 pronto."""
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from datetime import datetime, timezone
import hashlib, json


def build_import_package(original_mdb: bytes, modified_mdb: bytes, original_path: str, excel_bytes: bytes, changes, summary: dict, bridge_result: dict, mapping_csv: str = "") -> bytes:
    old_hash=hashlib.sha256(original_mdb).hexdigest()
    new_hash=hashlib.sha256(modified_mdb).hexdigest()
    if old_hash==new_hash and any(c.status=="alterar" for c in changes):
        raise ValueError("MDB original e atualizado são idênticos após suposta edição.")
    report={
        "formato":"SC-HDM4-importacao-v0.1",
        "gerado_utc":datetime.now(timezone.utc).isoformat(),
        "objeto":"Rede SC-110 — seções S1/S2",
        "arquivo_original":original_path,
        "hash_original_sha256":old_hash,
        "hash_atualizado_sha256":new_hash,
        "altera_objects_dat":False,
        "importacao_no_hdm4_necessaria":True,
        "resultado_driver":bridge_result,
        "resumo_planilha":summary,
        "alteracoes":[c.asdict() for c in changes],
    }
    steps=(
        "PACOTE DE IMPORTACAO HDM-4 — SC-110\n"
        "================================\n\n"
        "ATENCAO: ESTE ARQUIVO ZIP NAO E UM WORKSPACE HDM-4 PRONTO PARA EXECUTAR.\n"
        "OS ARQUIVOS objects.dat E objects.idx ORIGINAIS NAO FORAM MODIFICADOS.\n\n"
        "1. Faca um backup completo do workspace HDM-4 antes da importacao.\n"
        "2. Abra o HDM-4 v2.12.02 no Windows.\n"
        "3. Importe o arquivo de rede em 'Exports/SC-110_atualizado.mdb' no assistente nativo de importacao.\n"
        "4. Nao substitua a rede original sem validar em uma copia de testes.\n"
        "5. Confira o comprimento e os dados de S1 e S2 no HDM-4.\n"
        "6. Exporte a rede importada e compare os valores; so depois execute o estudo.\n"
        "7. Nao confunda RunData.mdb (resultados) com dados de entrada.\n\n"
        "ESCOPO v0.2: seis campos BASE validados; campos experimentais SECTIONS SOMENTE COM opt-in explicito.\n"
        "CUSTOS, TRAFEGO, FROTA E PADROES NAO SAO ALTERADOS NESTA VERSAO.\n"
        "A integracao para entregar objects.dat/objects.idx atualizados requer conector nativo validado.\n"
    )
    memory=BytesIO()
    with ZipFile(memory,"w",compression=ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr("LEIA-ME_ANTES_DE_IMPORTAR.txt",steps)
        z.writestr("Exports/SC-110_atualizado.mdb",modified_mdb)
        z.writestr("Auditoria/alteracoes.json",json.dumps(report,ensure_ascii=False,indent=2))
        z.writestr("Entradas/Dados_de_projeto_SC110.xlsx",excel_bytes)
        if mapping_csv:
            z.writestr("Auditoria/Mapeamento_Completo_SC110.csv",mapping_csv.encode("utf-8"))
    return memory.getvalue()
