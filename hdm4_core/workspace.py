"""Inspeção não destrutiva do workspace; objetos DAT/IDX jamais são modificados aqui."""
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile, BadZipFile
import hashlib

MAX_ZIP = 200 * 1024 * 1024
MAX_EXTRACT = 400 * 1024 * 1024

def inspect_zip(data: bytes):
    if len(data)>MAX_ZIP:
        raise ValueError("ZIP acima de 200 MB.")
    try:
        z=ZipFile(BytesIO(data))
    except BadZipFile as exc:
        raise ValueError("ZIP do workspace inválido.") from exc
    with z:
        infos=z.infolist()
        if len(infos)>3000 or sum(i.file_size for i in infos)>MAX_EXTRACT:
            raise ValueError("ZIP não permitido: número ou tamanho descompactado excessivo.")
        for i in infos:
            path=PurePosixPath(i.filename.replace("\\","/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("ZIP contém caminho inseguro.")
        names=z.namelist()
        dat=[n for n in names if n.lower().endswith("objects.dat")]
        idx=[n for n in names if n.lower().endswith("objects.idx")]
        exports=[n for n in names if "/exports/" in n.casefold() and n.casefold().endswith(".mdb")]
        network=[n for n in exports if PurePosixPath(n).name.casefold().startswith("sc-110,")]
        if len(dat)!=1 or len(idx)!=1 or len(network)!=1:
            raise ValueError(f"Estrutura inesperada: {len(dat)} DAT, {len(idx)} IDX e {len(network)} rede SC-110 em Exports.")
        mdb=z.read(network[0])
        if b"Standard Jet DB" not in mdb[:30]:
            raise ValueError("MDB de rede não possui cabeçalho Microsoft Jet esperado.")
        return {"dat":dat[0],"idx":idx[0],"network":network[0],"exports":exports,"size":len(mdb),"original_sha256":hashlib.sha256(mdb).hexdigest(),"file_count":len(names)}


def network_bytes(workspace: bytes, path: str)->bytes:
    with ZipFile(BytesIO(workspace)) as z:
        return z.read(path)
