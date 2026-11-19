"""Execução isolada do driver UCanAccess sem dependência de pyodbc/Windows.

Importante: a integração está implementada, mas requer validação com HDM-4
instalado. Falhas do driver impedem a geração do pacote, não são suprimidas.
"""
from __future__ import annotations
import base64
from pathlib import Path
from subprocess import run, TimeoutExpired
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request

VERSION = "5.3.0"
JAR_URL = f"https://repo1.maven.org/maven2/io/github/spannm/ucanaccess/{VERSION}/ucanaccess-{VERSION}-uber.jar"
BRIDGE_SOURCE = Path(__file__).resolve().parents[1] / "java" / "HdmMdbBridge.java"
CACHE = Path(tempfile.gettempdir()) / "sc_hdm4_java" 

class MDBError(Exception):
    pass


def driver_path(allow_download: bool = False) -> Path:
    local = os.environ.get("HDM4_UCANACCESS_JAR", "")
    if local:
        path = Path(local)
        if not path.is_file():
            raise MDBError(f"HDM4_UCANACCESS_JAR aponta para arquivo inexistente: {path}")
        return path
    path = CACHE / f"ucanaccess-{VERSION}-uber.jar"
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path
    if not allow_download:
        raise MDBError("Driver JDBC ainda não foi obtido; use 'Inspecionar MDB' para instalar o driver.")
    CACHE.mkdir(parents=True,exist_ok=True)
    part=path.with_suffix(".part")
    try:
        request = urllib.request.Request(JAR_URL, headers={"User-Agent": "SC-HDM4-Platform/0.1"})
        with urllib.request.urlopen(request, timeout=50) as response, part.open("wb") as out:
            if response.status != 200:
                raise MDBError(f"Download do driver retornou HTTP {response.status}.")
            # Limite contra resposta inválida/inesperada.
            total=0
            while True:
                piece=response.read(65536)
                if not piece: break
                total+=len(piece)
                if total > 50_000_000:
                    raise MDBError("Driver excedeu limite de download.")
                out.write(piece)
        if part.stat().st_size < 1_000_000 or part.open("rb").read(4)!=b"PK\x03\x04":
            raise MDBError("Driver baixado não é um JAR íntegro.")
        part.replace(path)
    except Exception as exc:
        part.unlink(missing_ok=True)
        raise MDBError(f"Não foi possível obter o driver JDBC: {exc}") from exc
    return path


def _java(mdb: Path, command: str, arg: str, allow_download=False):
    if not shutil.which("java"):
        raise MDBError("Java não instalado no servidor. Consulte packages.txt (JDK 17 ou superior).")
    jar=driver_path(allow_download=allow_download)
    cmd=["java", "-cp",str(jar),str(BRIDGE_SOURCE),command,str(mdb),arg]
    try:
        proc=run(cmd,capture_output=True,text=True,timeout=180)
    except TimeoutExpired as exc:
        raise MDBError("Consulta de MDB expirou (180 segundos).") from exc
    if proc.returncode:
        # A primeira linha da exceção informa a causa; a cauda normalmente só
        # contém pilha HSQLDB e escondia a mensagem útil na interface.
        lines = [line.strip() for line in (proc.stderr or proc.stdout).splitlines() if line.strip()]
        primary = next((line for line in lines if line.startswith("Exception in thread")), None)
        if primary is None:
            primary = next((line for line in lines if line.startswith(("java.", "net.ucanaccess."))), None)
        causes = [line for line in lines if line.startswith("Caused by:")]
        explanation = primary or (lines[0] if lines else "Erro desconhecido no Java")
        if causes:
            explanation += " | Causa mais interna: " + causes[-1]
        raise MDBError("A operação JDBC falhou: " + explanation[:1800])
    stdout=proc.stdout.strip().splitlines()
    if not stdout: raise MDBError("Ponte JDBC não retornou resultado.")
    try:
        return json.loads(stdout[-1])
    except ValueError as exc:
        raise MDBError("Resposta JSON inválida do driver: " + proc.stdout[-800:]) from exc


def inspect_tables(mdb: Path, allow_download=False):
    """Devolve tabelas e tipos de colunas (metadados JDBC, não grava nada)."""
    return _java(mdb,"tables","_",allow_download)


def snapshot(mdb: Path, table="SECTIONS", allow_download=False):
    return _java(mdb,"snapshot",table,allow_download)


def _enc(value):
    return base64.urlsafe_b64encode(str(value).encode("utf-8")).decode("ascii").rstrip("=")


def update_and_verify(mdb: Path, changes):
    edits=[c for c in changes if c.status=="alterar"]
    if not edits:
        raise MDBError("Não existem alterações efetivas selecionadas para aplicação.")
    with tempfile.NamedTemporaryFile(mode="w",suffix=".txt",encoding="utf-8",delete=False) as t:
        batch=Path(t.name)
        for c in edits:
            # SQL identifiers are whitelist-validated in Java; records are numerical.
            t.write("\t".join(map(_enc,["SECTIONS",c.chave,c.valor_chave,c.campo,c.antes,c.valor]))+"\n")
    try:
        result=_java(mdb,"apply",str(batch))
    finally:
        batch.unlink(missing_ok=True)
    if not result.get("ok") or result.get("alterados")!=len(edits):
        raise MDBError(f"Alterações aplicadas divergentes do plano: {result}")
    check=snapshot(mdb)
    original_id={str(row.get("SECT_ID", "")): row for row in check["rows"]}
    for c in edits:
        row=original_id.get(c.valor_chave)
        if not row or c.campo not in row or abs(float(row[c.campo])-c.valor)>1e-6:
            raise MDBError(f"Validação pós-gravação falhou: {c.secao}.{c.campo}.")
    return result
