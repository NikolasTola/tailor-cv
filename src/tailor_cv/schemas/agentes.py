"""Schemas das saídas estruturadas dos agentes de LLM.

São propositalmente simples (sem regex nem validadores complexos), porque viram
o JSON Schema enviado ao provedor. As regras de negócio ficam no código e no
validador de regras.
"""

from typing import Literal

from pydantic import BaseModel, Field

Senioridade = Literal[
    "estagio", "junior", "pleno", "senior", "especialista", "nao_informada"
]


class AnaliseVaga(BaseModel):
    cargo: str = Field(description="Cargo da vaga, como aparece no texto")
    senioridade: Senioridade
    resumo_vaga: str = Field(description="Uma frase sobre o que a vaga busca")
    requisitos_obrigatorios: list[str]
    requisitos_desejaveis: list[str]
    palavras_chave: list[str] = Field(
        description="Tecnologias, ferramentas e competências citadas na vaga"
    )
    headline: str = Field(description="Uma das opções de headline, copiada exatamente")


class AvaliacaoExperiencia(BaseModel):
    origem: str = Field(description="ID da experiência avaliada")
    nota: int = Field(description="Relevância para a vaga, de 0 a 10")
    justificativa: str = Field(description="Uma frase explicando a nota")


class BulletGerado(BaseModel):
    origem: list[str] = Field(description="ID(s) do(s) bullet(s) de origem (1 ou 2)")
    texto: str = Field(description="Bullet em português, na forma nominal")


class ExperienciaGerada(BaseModel):
    origem: str = Field(description="ID da experiência")
    cargo: str = Field(description="Cargo em português")
    bullets: list[BulletGerado]


class SaidaExperiencia(BaseModel):
    avaliacoes: list[AvaliacaoExperiencia] = Field(
        description="Uma avaliação para cada experiência recebida"
    )
    experiencias: list[ExperienciaGerada] = Field(
        description="Somente as experiências que devem entrar no currículo"
    )
