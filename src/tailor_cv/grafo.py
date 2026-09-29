"""Orquestração com LangGraph: o grafo completo, em ondas.

Onda 1  analisador, dados_pessoais, idiomas, formacao   (em paralelo)
Onda 2  titulo_e_nome, experiencia, cursos              (esperam o analisador)
Onda 3  habilidades, resumo                             (esperam experiência e cursos)
Onda 4  montar, validar_regras                          (esperam todos)

Cada nó avisa quando começa e termina (stream "custom"), o que alimenta o painel.
"""

import time
from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from tailor_cv.agentes import dados_pessoais, idiomas, titulo_e_nome
from tailor_cv.agentes.analisador import analisar_vaga
from tailor_cv.agentes.experiencia import selecionar_experiencias
from tailor_cv.agentes.secoes import (
    escrever_resumo,
    gerar_formacao,
    selecionar_cursos,
    selecionar_habilidades,
)
from tailor_cv.carregadores import I18n
from tailor_cv.config import Config
from tailor_cv.llm import ModeloEstruturado
from tailor_cv.schemas import BaseDados, Curriculo
from tailor_cv.schemas.agentes import AnaliseVaga, AvaliacaoExperiencia
from tailor_cv.schemas.curriculo import (
    Cabecalho,
    Curso,
    Experiencia,
    Formacao,
    Habilidade,
    Idioma,
)
from tailor_cv.validacao import ResultadoValidacao, validar_regras

# (nó, onda) na ordem em que aparecem no painel
NOS: list[tuple[str, int]] = [
    ("analisador", 1),
    ("dados_pessoais", 1),
    ("idiomas", 1),
    ("formacao", 1),
    ("titulo_e_nome", 2),
    ("experiencia", 2),
    ("cursos", 2),
    ("habilidades", 3),
    ("resumo", 3),
    ("montar", 4),
    ("validar_regras", 4),
]


class Estado(TypedDict, total=False):
    texto_vaga: str
    analise: AnaliseVaga
    titulo_nome: dict[str, str]
    dados: dict[str, str | None]
    idiomas: list[Idioma]
    formacao: list[Formacao]
    experiencias: list[Experiencia]
    avaliacoes: list[AvaliacaoExperiencia]
    omissoes: dict[str, str]
    cursos: list[Curso]
    habilidades: list[Habilidade]
    resumo: str
    curriculo: Curriculo
    validacao: ResultadoValidacao


def _com_status(
    nome: str, funcao: Callable[[Estado], Estado]
) -> Callable[[Estado], Estado]:
    """Envolve um nó para avisar o painel quando ele começa, termina ou falha."""

    def no(estado: Estado) -> Estado:
        avisar = get_stream_writer()
        avisar({"no": nome, "status": "rodando"})
        inicio = time.perf_counter()
        try:
            resultado = funcao(estado)
        except Exception:
            avisar(
                {"no": nome, "status": "erro", "segundos": time.perf_counter() - inicio}
            )
            raise
        status = "cache" if resultado.get("_cache") else "ok"
        avisar({"no": nome, "status": status, "segundos": time.perf_counter() - inicio})
        return {k: v for k, v in resultado.items() if not k.startswith("_")}

    return no


def construir_grafo(
    base: BaseDados,
    config: Config,
    i18n: I18n,
    llms: dict[str, ModeloEstruturado],
) -> CompiledStateGraph:
    def analisador(e: Estado) -> dict[str, Any]:
        if e.get("analise"):  # veio do cache
            return {"_cache": True}
        return {
            "analise": analisar_vaga(e["texto_vaga"], base.perfil, llms["analisador"])
        }

    def experiencia(e: Estado) -> Estado:
        exps, avaliacoes, omissoes = selecionar_experiencias(
            e["analise"], base, config, i18n, llms["experiencia"]
        )
        return {"experiencias": exps, "avaliacoes": avaliacoes, "omissoes": omissoes}

    def habilidades(e: Estado) -> Estado:
        return {
            "habilidades": selecionar_habilidades(
                e["analise"],
                e["experiencias"],
                e["cursos"],
                base,
                config,
                llms["habilidades"],
            )
        }

    def resumo(e: Estado) -> Estado:
        return {
            "resumo": escrever_resumo(
                e["analise"],
                e["experiencias"],
                e["cursos"],
                e["formacao"],
                base,
                config,
                llms["resumo"],
            )
        }

    def montar(e: Estado) -> Estado:
        cv = Curriculo(
            cabecalho=Cabecalho(**e["titulo_nome"], **e["dados"]),
            resumo=e["resumo"],
            experiencias=e["experiencias"],
            formacao=e["formacao"],
            cursos=e["cursos"],
            habilidades=e["habilidades"],
            idiomas=e["idiomas"],
        )
        return {"curriculo": cv}

    funcoes: dict[str, Callable[[Estado], Any]] = {
        "analisador": analisador,
        "dados_pessoais": lambda e: {"dados": dados_pessoais(base.perfil)},
        "idiomas": lambda e: {"idiomas": idiomas(base.idiomas, i18n)},
        "formacao": lambda e: {"formacao": gerar_formacao(base, llms["formacao"])},
        "titulo_e_nome": lambda e: {
            "titulo_nome": titulo_e_nome(base.perfil, e["analise"].headline)
        },
        "experiencia": experiencia,
        "cursos": lambda e: {
            "cursos": selecionar_cursos(e["analise"], base, config, llms["cursos"])
        },
        "habilidades": habilidades,
        "resumo": resumo,
        "montar": montar,
        "validar_regras": lambda e: {
            "validacao": validar_regras(e["curriculo"], base, i18n, config)
        },
    }

    grafo = StateGraph(Estado)
    for nome, _ in NOS:
        grafo.add_node(nome, _com_status(nome, funcoes[nome]))

    for nome in ("analisador", "dados_pessoais", "idiomas", "formacao"):
        grafo.add_edge(START, nome)
    for nome in ("titulo_e_nome", "experiencia", "cursos"):
        grafo.add_edge("analisador", nome)
    for nome in ("habilidades", "resumo"):
        grafo.add_edge(["experiencia", "cursos", "formacao"], nome)
    grafo.add_edge(
        ["titulo_e_nome", "dados_pessoais", "idiomas", "habilidades", "resumo"],
        "montar",
    )
    grafo.add_edge("montar", "validar_regras")
    grafo.add_edge("validar_regras", END)
    return grafo.compile()
