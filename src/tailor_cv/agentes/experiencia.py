"""Agente Experiência (LLM, onda 2).

A LLM decide só o que exige julgamento: nota de relevância, cargo traduzido e
bullets adaptados. Empresa, datas e modalidade vêm da origem por regra, então
nunca podem sair diferentes.
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from tailor_cv.agentes import prompts
from tailor_cv.agentes.deterministicos import modalidade
from tailor_cv.carregadores import I18n
from tailor_cv.config import Config
from tailor_cv.llm import ModeloEstruturado
from tailor_cv.schemas import BaseDados
from tailor_cv.schemas.agentes import (
    AnaliseVaga,
    AvaliacaoExperiencia,
    SaidaExperiencia,
)
from tailor_cv.schemas.curriculo import Bullet, Experiencia


def _experiencias_para_prompt(base: BaseDados) -> str:
    return json.dumps(
        [x.model_dump(exclude_none=True) for x in base.experiencias],
        ensure_ascii=False,
        indent=1,
    )


def selecionar_experiencias(
    analise: AnaliseVaga,
    base: BaseDados,
    config: Config,
    i18n: I18n,
    llm: ModeloEstruturado,
) -> tuple[list[Experiencia], list[AvaliacaoExperiencia]]:
    lim = config.limites
    sistema = prompts.EXPERIENCIA.format(
        nota_corte=lim.experiencias.nota_corte,
        nota_relevante=lim.experiencias.nota_relevante,
        rel_min=lim.experiencias.bullets_relevante[0],
        rel_max=lim.experiencias.bullets_relevante[1],
        sec_min=lim.experiencias.bullets_secundaria[0],
        sec_max=lim.experiencias.bullets_secundaria[1],
        bullet_max=lim.bullet_palavras_max,
    )
    mensagens = [
        SystemMessage(sistema),
        HumanMessage(
            f"Análise da vaga:\n{analise.model_dump_json(indent=1)}\n\n"
            f"Experiências:\n{_experiencias_para_prompt(base)}"
        ),
    ]
    saida: SaidaExperiencia = llm.with_structured_output(SaidaExperiencia).invoke(
        mensagens
    )

    # A decisão de incluir é por regra, a partir da nota: a LLM não pode
    # "esquecer" uma experiência obrigatória nem incluir uma abaixo do corte.
    notas = {a.origem: max(0, min(10, a.nota)) for a in saida.avaliacoes}
    origem_por_id = {x.id: x for x in base.experiencias}
    selecionadas: list[Experiencia] = []
    for gerada in saida.experiencias:
        origem = origem_por_id.get(gerada.origem)
        if origem is None:
            continue  # ID inventado: descartado aqui, nunca chega ao currículo
        incluir = origem.always_include or (
            notas.get(origem.id, 0) >= lim.experiencias.nota_corte
        )
        if not incluir or not gerada.bullets:
            continue
        selecionadas.append(
            Experiencia(
                origem=origem.id,
                empresa=origem.company,
                cargo=gerada.cargo,
                modalidade=modalidade(origem.work_mode, i18n),
                inicio=origem.start,
                fim=origem.end,
                bullets=[
                    Bullet(origem=b.origem, texto=b.texto) for b in gerada.bullets
                ],
            )
        )

    # Mais recente primeiro; emprego atual (fim = None) no topo
    selecionadas.sort(
        key=lambda x: (x.fim is None, x.fim or "", x.inicio), reverse=True
    )
    return selecionadas[: lim.experiencias.max], saida.avaliacoes
