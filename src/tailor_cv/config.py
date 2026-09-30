"""Leitura do config.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tailor_cv.carregadores import ErroDeOrigem


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Modelos(Base):
    analisador: str
    experiencia: str
    resumo: str
    formacao: str
    cursos: str
    habilidades: str
    validador: str


class LimitesExperiencias(Base):
    nota_corte: int = Field(ge=0, le=10)
    nota_relevante: int = Field(ge=0, le=10)
    max: int = Field(ge=1)
    bullets_relevante: tuple[int, int]
    bullets_secundaria: tuple[int, int]


class Limites(Base):
    paginas_max: int = Field(ge=1)
    retentativas_max: int = Field(default=2, ge=0, le=5)
    resumo_palavras_max: int = Field(ge=1)
    bullet_palavras_max: int = Field(ge=1)
    experiencias: LimitesExperiencias
    cursos_max: int = Field(ge=0)
    habilidades_max: int = Field(ge=0)


class Config(Base):
    modelos: Modelos
    limites: Limites
    palavras_proibidas: list[str] = []


def carregar_config(arquivo: Path = Path("config.yaml")) -> Config:
    if not arquivo.is_file():
        raise ErroDeOrigem(f"{arquivo}: arquivo de configuração não encontrado")
    dados = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
    try:
        return Config.model_validate(dados)
    except ValidationError as exc:
        erros = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        )
        raise ErroDeOrigem(f"{arquivo}: {erros}") from None