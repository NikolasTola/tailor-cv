"""Cache da análise da vaga: se o texto da vaga não mudou, não chama a LLM de novo."""

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from tailor_cv.schemas import Perfil
from tailor_cv.schemas.agentes import AnaliseVaga

PASTA_CACHE = Path("execucoes") / "cache"


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _arquivo(pasta: Path, nome_vaga: str) -> Path:
    return pasta / f"{nome_vaga}.analise.json"


def ler_analise(
    nome_vaga: str, texto_vaga: str, perfil: Perfil, pasta: Path = PASTA_CACHE
) -> AnaliseVaga | None:
    arquivo = _arquivo(pasta, nome_vaga)
    if not arquivo.is_file():
        return None
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        if dados.get("sha256") != _hash(texto_vaga):
            return None  # a vaga foi editada
        analise = AnaliseVaga.model_validate(dados["analise"])
    except (json.JSONDecodeError, KeyError, ValidationError):
        return None  # cache corrompido: ignora e refaz
    # a lista de headlines pode ter mudado desde a análise
    return analise if analise.headline in perfil.headlines else None


def salvar_analise(
    nome_vaga: str, texto_vaga: str, analise: AnaliseVaga, pasta: Path = PASTA_CACHE
) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    conteudo = {"sha256": _hash(texto_vaga), "analise": analise.model_dump()}
    _arquivo(pasta, nome_vaga).write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
