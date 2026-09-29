from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from tailor_cv.carregadores.origem import ErroDeOrigem
from tailor_cv.schemas.curriculo import Modalidade
from tailor_cv.schemas.origem import ModoTrabalho, Nivel


class I18n(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # dict com chave Literal: o Pydantic exige que todas as chaves sejam válidas
    niveis: dict[Nivel, str]
    idiomas: dict[str, str]
    modalidades: dict[ModoTrabalho, Modalidade]


def carregar_i18n(arquivo: Path = Path("i18n_pt.yaml")) -> I18n:
    if not arquivo.is_file():
        raise ErroDeOrigem(f"{arquivo}: arquivo de traduções não encontrado")
    dados = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
    try:
        i18n = I18n.model_validate(dados)
    except ValidationError as exc:
        erros = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        )
        raise ErroDeOrigem(f"{arquivo}: {erros}") from None

    faltando = set(Nivel.__args__) - set(i18n.niveis)
    if faltando:
        raise ErroDeOrigem(f"{arquivo}: faltam níveis: {', '.join(sorted(faltando))}")
    return i18n
