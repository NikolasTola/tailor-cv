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


class ProjetoGerado(BaseModel):
    origem: str = Field(description="ID do projeto")
    nome: str = Field(description="Nome do projeto em português")
    reconhecimento: str = Field(
        default="",
        description="Prêmio ou reconhecimento traduzido; vazio se a origem não tiver",
    )
    bullets: list[BulletGerado]


class SaidaProjetos(BaseModel):
    projetos: list[ProjetoGerado] = Field(
        description="Somente os projetos relevantes, do mais relevante para o menos"
    )


class FormacaoGerada(BaseModel):
    origem: str = Field(description="ID da formação")
    curso: str = Field(description="Nome do curso em português do Brasil")


class SaidaFormacao(BaseModel):
    formacoes: list[FormacaoGerada] = Field(description="Todas as formações recebidas")


class SaidaCursos(BaseModel):
    origens: list[str] = Field(
        description="IDs dos cursos escolhidos, do mais relevante para o menos"
    )


class HabilidadeEscolhida(BaseModel):
    origem: str = Field(description="Item copiado exatamente da lista de habilidades")
    texto: str = Field(description="Como a habilidade aparece no currículo")


class SaidaHabilidades(BaseModel):
    habilidades: list[HabilidadeEscolhida] = Field(
        description="Habilidades escolhidas, da mais relevante para a menos"
    )


class SaidaResumo(BaseModel):
    resumo: str = Field(description="Resumo profissional em português do Brasil")


TipoProblema = Literal[
    "sem_lastro", "inflacao", "traducao_errada", "forma_verbal", "termo_traduzido"
]
Veredito = Literal[
    "fiel",
    "sem_lastro",
    "inflacao",
    "traducao_errada",
    "forma_verbal",
    "termo_traduzido",
]


class AvaliacaoFidelidade(BaseModel):
    # A ordem dos campos importa: o modelo escreve a comparação antes de decidir.
    item: str = Field(description="ID do item, copiado exatamente da lista recebida")
    comparacao: str = Field(
        description=(
            "Compare o texto em português com a origem, em uma ou duas frases: os "
            "fatos são os mesmos? Cada número mede a mesma coisa, com o mesmo escopo?"
        )
    )
    veredito: Veredito
    trecho: str = Field(
        default="", description="Trecho em português com problema; vazio se fiel"
    )


class SaidaFidelidade(BaseModel):
    avaliacoes: list[AvaliacaoFidelidade] = Field(
        description="Uma avaliação para cada item recebido, na mesma ordem"
    )
