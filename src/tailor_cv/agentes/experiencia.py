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
    correcoes: list[str] | None = None,
) -> tuple[list[Experiencia], list[AvaliacaoExperiencia], dict[str, str]]:
    """Devolve as experiências selecionadas, as avaliações da LLM e, para cada
    experiência omitida, o motivo da omissão."""
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
            prompts.com_correcoes(
                f"Análise da vaga:\n{analise.model_dump_json(indent=1)}\n\n"
                f"Experiências:\n{_experiencias_para_prompt(base)}",
                correcoes,
            )
        ),
    ]
    saida: SaidaExperiencia = llm.with_structured_output(SaidaExperiencia).invoke(
        mensagens
    )

    # A decisão de incluir é por regra, a partir da nota: a LLM não pode
    # "esquecer" uma experiência obrigatória nem incluir uma abaixo do corte.
    corte = lim.experiencias.nota_corte
    notas = {a.origem: max(0, min(10, a.nota)) for a in saida.avaliacoes}
    geradas = {g.origem: g for g in saida.experiencias if g.bullets}
    selecionadas: list[Experiencia] = []
    omissoes: dict[str, str] = {}
    for origem in base.experiencias:
        deve_entrar = origem.always_include or notas.get(origem.id, 0) >= corte
        gerada = geradas.get(origem.id)
        if origem.id not in notas and not origem.always_include:
            omissoes[origem.id] = "a LLM não avaliou esta experiência"
        elif not deve_entrar:
            omissoes[origem.id] = f"nota abaixo do corte ({corte})"
        elif gerada is None:
            omissoes[origem.id] = "a LLM não gerou bullets, apesar da nota"
        else:
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
    # IDs inventados pela LLM nunca entram: o laço acima só percorre a base

    # Mais recente primeiro; emprego atual (fim = None) no topo
    selecionadas.sort(
        key=lambda x: (x.fim is None, x.fim or "", x.inicio), reverse=True
    )
    maximo = lim.experiencias.max
    for excedente in selecionadas[maximo:]:
        omissoes[excedente.origem] = f"acima do limite de {maximo} experiências"
    return selecionadas[:maximo], saida.avaliacoes, omissoes
