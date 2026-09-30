"""Orquestração com LangGraph: o grafo completo, em ondas, com correção automática.

Onda 1  analisador, dados_pessoais, idiomas, formacao   (em paralelo)
Onda 2  titulo_e_nome, experiencia, cursos              (esperam o analisador)
Onda 3  habilidades, resumo                             (esperam experiência e cursos)
Onda 4  montar, validar_regras, validar_fidelidade

A fidelidade (LLM) só roda se as regras (grátis) passarem. Se alguma validação
bloquear, o nó "corrigir" refaz só os agentes responsáveis, e os que dependem deles,
com os problemas no prompt; depois o currículo é montado e validado de novo.

Cada nó avisa quando começa e termina (stream "custom"), o que alimenta o painel.
"""

import contextvars
import operator
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, TypedDict

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
from tailor_cv.validacao import (
    Problema,
    ResultadoValidacao,
    validar_fidelidade,
    validar_regras,
)

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
    ("validar_fidelidade", 4),
    ("corrigir", 4),
]

# Agentes que uma nova chamada de LLM pode corrigir, e quem depende de cada um.
# Bloqueios de agentes de regra (dados pessoais, idiomas) vêm dos arquivos de
# origem: repetir não adianta, então a execução é abortada.
DEPENDENTES: dict[str, set[str]] = {
    "experiencia": {"habilidades", "resumo"},
    "cursos": {"habilidades", "resumo"},
    "formacao": {"resumo"},
    "habilidades": set(),
    "resumo": set(),
}
PRIMEIRA_LEVA = ("experiencia", "cursos", "formacao")
SEGUNDA_LEVA = ("habilidades", "resumo")


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
    fidelidade: ResultadoValidacao | None
    tentativas: int
    historico: Annotated[list[dict[str, Any]], operator.add]


def _com_status(nome: str, funcao: Callable[[Estado], Any]) -> Callable[[Estado], Any]:
    """Envolve um nó para avisar o painel quando ele começa, termina ou falha."""

    def no(estado: Estado) -> dict[str, Any]:
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


def bloqueios_atuais(e: Estado) -> list[Problema]:
    """Os bloqueios da validação que falhou por último."""
    if not e["validacao"].aprovado:
        return e["validacao"].bloqueios
    fidelidade = e.get("fidelidade")
    return fidelidade.bloqueios if fidelidade else []


def _pode_corrigir(e: Estado, config: Config) -> bool:
    bloqueios = bloqueios_atuais(e)
    return (
        bool(bloqueios)
        and e.get("tentativas", 0) < config.limites.retentativas_max
        and all(p.agente in DEPENDENTES for p in bloqueios)
    )


def construir_grafo(
    base: BaseDados,
    config: Config,
    i18n: I18n,
    llms: dict[str, ModeloEstruturado],
) -> CompiledStateGraph:
    # ----- agentes de LLM que podem ser refeitos com correções -----
    def experiencia(e: Estado, correcoes: list[str] | None = None) -> Estado:
        exps, avaliacoes, omissoes = selecionar_experiencias(
            e["analise"], base, config, i18n, llms["experiencia"], correcoes
        )
        return {"experiencias": exps, "avaliacoes": avaliacoes, "omissoes": omissoes}

    def cursos(e: Estado, correcoes: list[str] | None = None) -> Estado:
        return {
            "cursos": selecionar_cursos(
                e["analise"], base, config, llms["cursos"], correcoes
            )
        }

    def formacao(e: Estado, correcoes: list[str] | None = None) -> Estado:
        return {"formacao": gerar_formacao(base, llms["formacao"], correcoes)}

    def habilidades(e: Estado, correcoes: list[str] | None = None) -> Estado:
        return {
            "habilidades": selecionar_habilidades(
                e["analise"],
                e["experiencias"],
                e["cursos"],
                base,
                config,
                llms["habilidades"],
                correcoes,
            )
        }

    def resumo(e: Estado, correcoes: list[str] | None = None) -> Estado:
        return {
            "resumo": escrever_resumo(
                e["analise"],
                e["experiencias"],
                e["cursos"],
                e["formacao"],
                base,
                config,
                llms["resumo"],
                correcoes,
            )
        }

    corrigiveis: dict[str, Callable[..., Estado]] = {
        "experiencia": experiencia,
        "cursos": cursos,
        "formacao": formacao,
        "habilidades": habilidades,
        "resumo": resumo,
    }

    # ----- demais nós -----
    def analisador(e: Estado) -> dict[str, Any]:
        if e.get("analise"):  # veio do cache
            return {"_cache": True}
        return {
            "analise": analisar_vaga(e["texto_vaga"], base.perfil, llms["analisador"])
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

    def corrigir(e: Estado) -> dict[str, Any]:
        """Refaz os agentes responsáveis pelos bloqueios, em duas levas paralelas."""
        avisar = get_stream_writer()
        tentativa = e.get("tentativas", 0) + 1
        bloqueios = bloqueios_atuais(e)
        correcoes: dict[str, list[str]] = {}
        for p in bloqueios:
            correcoes.setdefault(p.agente, []).append(f"{p.local}: {p.mensagem}")
        refazer = set(correcoes)
        for agente in correcoes:
            refazer |= DEPENDENTES[agente]

        atual: dict[str, Any] = dict(e)

        def rodar(agente: str) -> Estado:
            avisar({"no": agente, "status": "rodando", "tentativa": tentativa})
            inicio = time.perf_counter()
            try:
                resultado = corrigiveis[agente](atual, correcoes.get(agente))
            except Exception:
                avisar({"no": agente, "status": "erro", "tentativa": tentativa})
                raise
            avisar(
                {
                    "no": agente,
                    "status": "ok",
                    "segundos": time.perf_counter() - inicio,
                    "tentativa": tentativa,
                }
            )
            return resultado

        for leva in (PRIMEIRA_LEVA, SEGUNDA_LEVA):
            agentes = [a for a in leva if a in refazer]
            with ThreadPoolExecutor() as executor:
                # cada thread recebe uma cópia do contexto do LangGraph, necessária
                # para os avisos ao painel e para o tracing
                futuros = [
                    executor.submit(contextvars.copy_context().run, rodar, a)
                    for a in agentes
                ]
                for futuro in futuros:
                    atual.update(futuro.result())

        novos = {k: atual[k] for k in atual if k not in e or atual[k] is not e.get(k)}
        return {
            **novos,
            "tentativas": tentativa,
            "fidelidade": None,  # o resultado anterior não vale para o currículo novo
            "historico": [
                {
                    "tentativa": tentativa,
                    "bloqueios": [str(p) for p in bloqueios],
                    "refeitos": sorted(refazer),
                }
            ],
        }

    funcoes: dict[str, Callable[[Estado], Any]] = {
        "analisador": analisador,
        "dados_pessoais": lambda e: {"dados": dados_pessoais(base.perfil)},
        "idiomas": lambda e: {"idiomas": idiomas(base.idiomas, i18n)},
        "formacao": formacao,
        "titulo_e_nome": lambda e: {
            "titulo_nome": titulo_e_nome(base.perfil, e["analise"].headline)
        },
        "experiencia": experiencia,
        "cursos": cursos,
        "habilidades": habilidades,
        "resumo": resumo,
        "montar": montar,
        "validar_regras": lambda e: {
            "validacao": validar_regras(e["curriculo"], base, i18n, config)
        },
        "validar_fidelidade": lambda e: {
            "fidelidade": validar_fidelidade(e["curriculo"], base, llms["validador"])
        },
        "corrigir": corrigir,
    }

    def depois_das_regras(e: Estado) -> str:
        if e["validacao"].aprovado:
            return "validar_fidelidade"
        return "corrigir" if _pode_corrigir(e, config) else END

    def depois_da_fidelidade(e: Estado) -> str:
        fidelidade = e.get("fidelidade")
        if fidelidade is None or fidelidade.aprovado:
            return END
        return "corrigir" if _pode_corrigir(e, config) else END

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
    grafo.add_conditional_edges(
        "validar_regras", depois_das_regras, ["validar_fidelidade", "corrigir", END]
    )
    grafo.add_conditional_edges(
        "validar_fidelidade", depois_da_fidelidade, ["corrigir", END]
    )
    grafo.add_edge("corrigir", "montar")
    return grafo.compile()
