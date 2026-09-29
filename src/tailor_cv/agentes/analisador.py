"""Agente Analisador da vaga (LLM, onda 1)."""

from langchain_core.messages import HumanMessage, SystemMessage

from tailor_cv.agentes import prompts
from tailor_cv.agentes.deterministicos import ErroDeRegra
from tailor_cv.llm import ModeloEstruturado
from tailor_cv.schemas import Perfil
from tailor_cv.schemas.agentes import AnaliseVaga


def analisar_vaga(
    texto_vaga: str, perfil: Perfil, llm: ModeloEstruturado
) -> AnaliseVaga:
    opcoes = "\n".join(f"- {h}" for h in perfil.headlines)
    mensagens = [
        SystemMessage(prompts.ANALISADOR.format(headlines=opcoes)),
        HumanMessage(f"Texto da vaga:\n\n{texto_vaga}"),
    ]
    analise: AnaliseVaga = llm.with_structured_output(AnaliseVaga).invoke(mensagens)

    if analise.headline not in perfil.headlines:
        raise ErroDeRegra(
            f"o Analisador escolheu o headline {analise.headline!r}, que não está "
            "na lista aprovada do perfil.yaml"
        )
    return analise
