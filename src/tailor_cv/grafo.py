"""Orquestração com LangGraph.

Etapa 3: grafo mínimo com o Analisador da vaga e o agente de Experiência.
As ondas completas, em paralelo, entram na Etapa 4.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from tailor_cv.agentes.analisador import analisar_vaga
from tailor_cv.agentes.experiencia import selecionar_experiencias
from tailor_cv.carregadores import I18n
from tailor_cv.config import Config
from tailor_cv.llm import ModeloEstruturado
from tailor_cv.schemas import BaseDados
from tailor_cv.schemas.agentes import AnaliseVaga, AvaliacaoExperiencia
from tailor_cv.schemas.curriculo import Experiencia


class Estado(TypedDict, total=False):
    texto_vaga: str
    analise: AnaliseVaga
    experiencias: list[Experiencia]
    avaliacoes: list[AvaliacaoExperiencia]


def construir_grafo(
    base: BaseDados,
    config: Config,
    i18n: I18n,
    llms: dict[str, ModeloEstruturado],
) -> CompiledStateGraph:
    """Cada nó lê o estado e devolve só as chaves que ele produz."""

    def no_analisador(estado: Estado) -> Estado:
        return {
            "analise": analisar_vaga(
                estado["texto_vaga"], base.perfil, llms["analisador"]
            )
        }

    def no_experiencia(estado: Estado) -> Estado:
        experiencias, avaliacoes = selecionar_experiencias(
            estado["analise"], base, config, i18n, llms["experiencia"]
        )
        return {"experiencias": experiencias, "avaliacoes": avaliacoes}

    def inicio(estado: Estado) -> str:
        # com a análise em cache, o Analisador é pulado
        return "experiencia" if estado.get("analise") else "analisador"

    grafo = StateGraph(Estado)
    grafo.add_node("analisador", no_analisador)
    grafo.add_node("experiencia", no_experiencia)
    grafo.add_conditional_edges(START, inicio, ["analisador", "experiencia"])
    grafo.add_edge("analisador", "experiencia")
    grafo.add_edge("experiencia", END)
    return grafo.compile()
