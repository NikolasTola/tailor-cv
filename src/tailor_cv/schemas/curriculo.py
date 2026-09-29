from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

AnoMes = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Modalidade = Literal["Remoto", "Híbrido", "Presencial"]
# Um bullet pode fundir até dois bullets da mesma experiência: aceita "id" ou ["id1", "id2"]
Origens = Annotated[
    list[Texto],
    BeforeValidator(lambda v: [v] if isinstance(v, str) else v),
    Field(min_length=1),
]


class Base(BaseModel):
    # extra="forbid": um campo digitado errado numa edição manual do JSON vira erro, não é ignorado
    model_config = ConfigDict(extra="forbid")


class Cabecalho(Base):
    nome: Texto
    headline: Texto
    cidade: Texto
    telefone: Texto
    email: Texto
    linkedin: Texto
    github: Texto | None = None


class Bullet(Base):
    origem: Origens = Field(description="ID(s) do(s) bullet(s) de origem")
    texto: Texto


class Experiencia(Base):
    origem: Texto = Field(description="ID do arquivo de experiência de origem")
    empresa: Texto
    cargo: Texto
    modalidade: Modalidade | None = None
    inicio: AnoMes
    fim: AnoMes | None = Field(default=None, description="None = emprego atual")
    bullets: list[Bullet] = Field(min_length=1)

    @model_validator(mode="after")
    def fim_depois_do_inicio(self) -> "Experiencia":
        # "YYYY-MM" em ordem alfabética é também ordem cronológica
        if self.fim is not None and self.fim < self.inicio:
            raise ValueError(f"fim ({self.fim}) é anterior ao início ({self.inicio})")
        return self


class Formacao(Base):
    origem: Texto
    curso: Texto
    instituicao: Texto
    conclusao: Texto


class Curso(Base):
    origem: Texto
    nome: Texto
    instituicao: Texto
    ano: Texto | None = None


class Habilidade(Base):
    origem: Texto = Field(description="Item exato do habilidades.md")
    texto: Texto = Field(description="Como aparece no currículo")


class Idioma(Base):
    idioma: Texto
    nivel: Texto


class Curriculo(Base):
    cabecalho: Cabecalho
    resumo: Texto
    experiencias: list[Experiencia] = Field(min_length=1)
    formacao: list[Formacao] = []
    cursos: list[Curso] = []
    habilidades: list[Habilidade] = []
    idiomas: list[Idioma] = []
