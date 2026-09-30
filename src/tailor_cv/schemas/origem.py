"""Schemas dos arquivos de origem (a base de dados pessoal, em inglês)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

AnoMes = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
Nivel = Literal["native", "fluent", "advanced", "intermediate", "basic"]
ModoTrabalho = Literal["remote", "hybrid", "onsite"]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Perfil(Base):
    name: Texto
    city: Texto
    phone: Texto
    email: Texto
    linkedin: Texto
    github: Texto | None = None
    headlines: list[Texto] = Field(
        min_length=1, description="Títulos aprovados, em português"
    )


class Conquista(Base):
    id: Slug
    text: Texto
    tech: list[Texto] = []
    metric: Texto | None = None


class ExperienciaOrigem(Base):
    id: Slug
    company: Texto
    role: Texto
    start: AnoMes
    end: AnoMes | None = None  # None = emprego atual ("present" no arquivo)
    location: Texto | None = None
    work_mode: ModoTrabalho | None = None
    always_include: bool = False
    context: Texto | None = None
    achievements: list[Conquista] = Field(min_length=1)

    @model_validator(mode="after")
    def validar(self) -> "ExperienciaOrigem":
        if self.end is not None and self.end < self.start:
            raise ValueError(f"end ({self.end}) é anterior a start ({self.start})")
        ids = [a.id for a in self.achievements]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(f"IDs de bullet repetidos: {', '.join(repetidos)}")
        return self


class ProjetoOrigem(Base):
    id: Slug
    name: Texto
    type: Literal["academic", "personal"] = "personal"
    year: int | None = Field(default=None, ge=1950, le=2100)
    url: Texto | None = None
    award: Texto | None = None
    tech: list[Texto] = []
    context: Texto | None = None
    achievements: list[Conquista] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_de_bullet_unicos(self) -> "ProjetoOrigem":
        ids = [a.id for a in self.achievements]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(f"IDs de bullet repetidos: {', '.join(repetidos)}")
        return self


class FormacaoOrigem(Base):
    id: Slug
    degree: Texto
    institution: Texto
    completion: int = Field(
        ge=1950, le=2100, description="Ano de conclusão (ou previsão)"
    )
    in_progress: bool = False
    notes: Texto | None = None


class CursoOrigem(Base):
    id: Slug
    name: Texto
    provider: Texto
    year: int | None = Field(default=None, ge=1950, le=2100)
    kind: Literal["course", "certification"] = "course"
    tech: list[Texto] = []


class Habilidades(Base):
    technical: list[Texto] = []
    behavioral: list[Texto] = []


class IdiomaOrigem(Base):
    language: Texto
    level: Nivel


class BaseDados(Base):
    perfil: Perfil
    experiencias: list[ExperienciaOrigem] = Field(min_length=1)
    projetos: list[ProjetoOrigem] = []
    formacao: list[FormacaoOrigem] = []
    cursos: list[CursoOrigem] = []
    habilidades: Habilidades
    idiomas: list[IdiomaOrigem] = []

    @model_validator(mode="after")
    def ids_unicos(self) -> "BaseDados":
        for nome, itens in (
            ("experiencias", self.experiencias),
            ("projetos", self.projetos),
            ("formacao", self.formacao),
            ("cursos", self.cursos),
        ):
            ids = [i.id for i in itens]
            repetidos = sorted({i for i in ids if ids.count(i) > 1})
            if repetidos:
                raise ValueError(f"IDs repetidos em {nome}/: {', '.join(repetidos)}")
        return self
