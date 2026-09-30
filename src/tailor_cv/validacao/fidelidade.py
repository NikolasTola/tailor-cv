"""Validador de fidelidade (onda 4, LLM): confere o sentido do currículo em português
contra a origem em inglês. Pega o que regras fixas não pegam: inflação, escopo de
métrica, curso apresentado como especialização, tradução que muda o sentido.

Deve usar um modelo de provedor diferente dos geradores (config.yaml: validador).
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from tailor_cv.agentes import prompts
from tailor_cv.llm import ModeloEstruturado
from tailor_cv.schemas import BaseDados, Curriculo
from tailor_cv.schemas.agentes import SaidaFidelidade
from tailor_cv.validacao.regras import Agente, Problema, ResultadoValidacao

BLOQUEIAM = {"sem_lastro", "inflacao", "traducao_errada"}


def _itens(cv: Curriculo, base: BaseDados) -> dict[str, dict]:
    """Monta os pares (texto em português, origem) e o agente responsável por cada um."""
    exps = {x.id: x for x in base.experiencias}
    itens: dict[str, dict] = {}
    for x in cv.experiencias:
        origem = exps.get(x.origem)
        if origem is None:
            continue
        conquistas = {a.id: a for a in origem.achievements}
        itens[f"exp:{x.origem}:cargo"] = {
            "agente": "experiencia",
            "texto_pt": x.cargo,
            "origem": origem.role,
        }
        for i, b in enumerate(x.bullets):
            fontes = [conquistas[o] for o in b.origem if o in conquistas]
            itens[f"exp:{x.origem}:bullet:{i}"] = {
                "agente": "experiencia",
                "texto_pt": b.texto,
                # a origem inclui as tags: as tecnologias usadas podem ser citadas
                "origem": [
                    a.model_dump(include={"text", "tech", "metric"}, exclude_none=True)
                    for a in fontes
                ],
            }

    formacoes = {f.id: f for f in base.formacao}
    for f in cv.formacao:
        if f.origem in formacoes:
            itens[f"formacao:{f.origem}"] = {
                "agente": "formacao",
                "texto_pt": f.curso,
                "origem": formacoes[f.origem].degree,
            }

    comportamentais = set(base.habilidades.behavioral)
    for h in cv.habilidades:
        if h.origem in comportamentais:
            itens[f"habilidade:{h.origem}"] = {
                "agente": "habilidades",
                "texto_pt": h.texto,
                "origem": h.origem,
            }

    itens["resumo"] = {
        "agente": "resumo",
        "texto_pt": cv.resumo,
        "origem": {
            "cargos": [x.cargo for x in cv.experiencias],
            "bullets": [b.texto for x in cv.experiencias for b in x.bullets],
            "cursos": [c.nome for c in cv.cursos],
            "formacao": [f.curso for f in cv.formacao],
            "habilidades": [h.texto for h in cv.habilidades],
        },
    }
    return itens


def validar_fidelidade(
    cv: Curriculo, base: BaseDados, llm: ModeloEstruturado
) -> ResultadoValidacao:
    itens = _itens(cv, base)
    para_llm = [
        {"id": id_, "texto_pt": i["texto_pt"], "origem": i["origem"]}
        for id_, i in itens.items()
    ]
    mensagens = [
        SystemMessage(prompts.FIDELIDADE),
        HumanMessage(f"Itens:\n{json.dumps(para_llm, ensure_ascii=False, indent=1)}"),
    ]
    saida: SaidaFidelidade = llm.with_structured_output(SaidaFidelidade).invoke(
        mensagens
    )

    resultado = ResultadoValidacao()
    for a in saida.avaliacoes:
        item = itens.get(a.item)
        if item is None or a.veredito == "fiel":
            continue  # ID inventado pelo validador ou item aprovado
        agente: Agente = item["agente"]
        trecho = a.trecho or item["texto_pt"]
        problema = Problema(
            agente=agente,
            verificacao=a.veredito,
            local=a.item,
            mensagem=f"{trecho!r}: {a.comparacao}",
        )
        if a.veredito in BLOQUEIAM:
            resultado.bloqueios.append(problema)
        else:
            resultado.alertas.append(problema)
    return resultado