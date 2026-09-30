"""Agentes das seções Formação, Cursos (onda 2), Habilidades e Resumo (onda 3).

Mesmo padrão do agente de Experiência: a LLM escolhe, ordena ou escreve; os fatos
(instituição, ano, nome do curso, itens permitidos) vêm da origem por código.
"""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from tailor_cv.agentes import prompts
from tailor_cv.config import Config
from tailor_cv.llm import ModeloEstruturado
from tailor_cv.schemas import BaseDados
from tailor_cv.schemas.agentes import (
    AnaliseVaga,
    SaidaCursos,
    SaidaFormacao,
    SaidaHabilidades,
    SaidaProjetos,
    SaidaResumo,
)
from tailor_cv.schemas.curriculo import (
    Bullet,
    Curso,
    Experiencia,
    Formacao,
    Habilidade,
    Projeto,
)


def _json(dados: object) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=1)


def _chamar[T](
    llm: ModeloEstruturado,
    schema: type[T],
    sistema: str,
    humano: str,
    correcoes: list[str] | None = None,
) -> T:
    humano = prompts.com_correcoes(humano, correcoes)
    mensagens = [SystemMessage(sistema), HumanMessage(humano)]
    return llm.with_structured_output(schema).invoke(mensagens)


# ---------- Formação ----------


def gerar_formacao(
    base: BaseDados, llm: ModeloEstruturado, correcoes: list[str] | None = None
) -> list[Formacao]:
    """Traduz os nomes dos cursos. Todas as formações entram, da mais recente à mais antiga."""
    if not base.formacao:
        return []
    entrada = [{"id": f.id, "degree": f.degree} for f in base.formacao]
    saida = _chamar(
        llm, SaidaFormacao, prompts.FORMACAO, f"Formações:\n{_json(entrada)}", correcoes
    )
    traducoes = {g.origem: g.curso.strip() for g in saida.formacoes if g.curso.strip()}

    formacoes = []
    for f in sorted(base.formacao, key=lambda f: f.completion, reverse=True):
        conclusao = f"{f.completion} (previsão)" if f.in_progress else str(f.completion)
        formacoes.append(
            Formacao(
                origem=f.id,
                # se a LLM pular uma formação, ela entra com o nome original
                curso=traducoes.get(f.id, f.degree),
                instituicao=f.institution,
                conclusao=conclusao,
            )
        )
    return formacoes


# ---------- Cursos ----------


def selecionar_cursos(
    analise: AnaliseVaga,
    base: BaseDados,
    config: Config,
    llm: ModeloEstruturado,
    correcoes: list[str] | None = None,
) -> list[Curso]:
    """Escolhe e ordena por relevância. Nomes ficam como na origem (são nomes próprios)."""
    if not base.cursos:
        return []
    maximo = config.limites.cursos_max
    entrada = [c.model_dump(exclude_none=True) for c in base.cursos]
    saida = _chamar(
        llm,
        SaidaCursos,
        prompts.CURSOS.format(maximo=maximo),
        f"Análise da vaga:\n{analise.model_dump_json(indent=1)}\n\n"
        f"Cursos e certificações:\n{_json(entrada)}",
        correcoes,
    )
    por_id = {c.id: c for c in base.cursos}
    escolhidos = list(dict.fromkeys(o for o in saida.origens if o in por_id))
    return [
        Curso(
            origem=c.id,
            nome=c.name,
            instituicao=c.provider,
            ano=str(c.year) if c.year else None,
        )
        for c in (por_id[o] for o in escolhidos[:maximo])
    ]


# ---------- Projetos ----------


def selecionar_projetos(
    analise: AnaliseVaga,
    base: BaseDados,
    config: Config,
    llm: ModeloEstruturado,
    correcoes: list[str] | None = None,
) -> list[Projeto]:
    """Escolhe, ordena e escreve os projetos. Ano, link e existência do prêmio vêm
    da origem: sem "award" na origem, nenhum reconhecimento entra."""
    maximo = config.limites.projetos_max
    if not base.projetos or maximo == 0:
        return []
    entrada = [p.model_dump(exclude_none=True) for p in base.projetos]
    saida = _chamar(
        llm,
        SaidaProjetos,
        prompts.PROJETOS.format(
            maximo=maximo, bullet_max=config.limites.bullet_palavras_max
        ),
        f"Análise da vaga:\n{analise.model_dump_json(indent=1)}\n\n"
        f"Projetos:\n{_json(entrada)}",
        correcoes,
    )
    por_id = {p.id: p for p in base.projetos}
    projetos: list[Projeto] = []
    vistos: set[str] = set()
    for gerado in saida.projetos:
        origem = por_id.get(gerado.origem)
        if origem is None or origem.id in vistos or not gerado.bullets:
            continue  # ID inventado, repetido ou sem conteúdo
        vistos.add(origem.id)
        reconhecimento = gerado.reconhecimento.strip() if origem.award else ""
        projetos.append(
            Projeto(
                origem=origem.id,
                nome=gerado.nome.strip() or origem.name,
                ano=str(origem.year) if origem.year else None,
                url=origem.url,
                reconhecimento=reconhecimento or None,
                bullets=[
                    Bullet(origem=b.origem, texto=b.texto) for b in gerado.bullets
                ],
            )
        )
    return projetos[:maximo]


# ---------- Habilidades ----------


def evidencias(
    experiencias: list[Experiencia],
    cursos: list[Curso],
    base: BaseDados,
    projetos: list[Projeto] | None = None,
) -> list[str]:
    """Tecnologias das experiências, cursos e projetos já selecionados."""
    conquistas = {a.id: a for x in base.experiencias for a in x.achievements}
    tags = [
        t
        for x in experiencias
        for b in x.bullets
        for o in b.origem
        if o in conquistas
        for t in conquistas[o].tech
    ]
    cursos_base = {c.id: c for c in base.cursos}
    tags += [
        t for c in cursos if c.origem in cursos_base for t in cursos_base[c.origem].tech
    ]
    projetos_base = {p.id: p for p in base.projetos}
    for p in projetos or []:
        origem = projetos_base.get(p.origem)
        if origem is None:
            continue
        tags += origem.tech
        conquistas_p = {a.id: a for a in origem.achievements}
        tags += [
            t
            for b in p.bullets
            for o in b.origem
            if o in conquistas_p
            for t in conquistas_p[o].tech
        ]
    return list(dict.fromkeys(tags))


def _pedida_na_vaga(habilidade: str, analise: AnaliseVaga) -> bool:
    """'AWS Bedrock' casa com 'AWS (Bedrock, ECS ou Lambda)': todas as palavras da
    habilidade aparecem num mesmo item da vaga."""
    palavras = set(re.findall(r"\w+", habilidade.lower()))
    itens = [
        *analise.requisitos_obrigatorios,
        *analise.requisitos_desejaveis,
        *analise.palavras_chave,
    ]
    return any(palavras <= set(re.findall(r"\w+", item.lower())) for item in itens)


def tecnicas_permitidas(
    analise: AnaliseVaga,
    experiencias: list[Experiencia],
    cursos: list[Curso],
    base: BaseDados,
    projetos: list[Projeto] | None = None,
) -> list[str]:
    """Técnicas com evidência no currículo ou pedidas na vaga, na ordem do arquivo."""
    comprovadas = {t.lower() for t in evidencias(experiencias, cursos, base, projetos)}
    return [
        t
        for t in base.habilidades.technical
        if t.lower() in comprovadas or _pedida_na_vaga(t, analise)
    ]


def selecionar_habilidades(
    analise: AnaliseVaga,
    experiencias: list[Experiencia],
    cursos: list[Curso],
    base: BaseDados,
    config: Config,
    llm: ModeloEstruturado,
    correcoes: list[str] | None = None,
    projetos: list[Projeto] | None = None,
) -> list[Habilidade]:
    # a LLM só vê as técnicas permitidas; o filtro abaixo garante a regra mesmo
    # que ela devolva outra
    tecnicas = tecnicas_permitidas(analise, experiencias, cursos, base, projetos)
    comportamentais = base.habilidades.behavioral
    if not tecnicas and not comportamentais:
        return []
    maximo = config.limites.habilidades_max
    entrada = {"technical": tecnicas, "behavioral": comportamentais}
    saida = _chamar(
        llm,
        SaidaHabilidades,
        prompts.HABILIDADES.format(maximo=maximo),
        f"Análise da vaga:\n{analise.model_dump_json(indent=1)}\n\n"
        f"Habilidades da candidata:\n{_json(entrada)}\n\n"
        f"Tecnologias já selecionadas:\n{_json(evidencias(experiencias, cursos, base, projetos))}",
        correcoes,
    )

    escolhidas: dict[str, Habilidade] = {}
    for h in saida.habilidades:
        if h.origem in escolhidas:
            continue
        if h.origem in tecnicas:
            # técnica nunca é traduzida, mesmo que a LLM tente
            escolhidas[h.origem] = Habilidade(origem=h.origem, texto=h.origem)
        elif h.origem in comportamentais and h.texto.strip():
            escolhidas[h.origem] = Habilidade(origem=h.origem, texto=h.texto.strip())
        # qualquer outro item é inventado ou sem evidência e fica de fora

    # técnicas primeiro, mantendo a ordem de relevância dentro de cada grupo
    lista = sorted(escolhidas.values(), key=lambda h: h.origem not in tecnicas)
    return lista[:maximo]


# ---------- Resumo ----------


def escrever_resumo(
    analise: AnaliseVaga,
    experiencias: list[Experiencia],
    cursos: list[Curso],
    formacao: list[Formacao],
    base: BaseDados,
    config: Config,
    llm: ModeloEstruturado,
    correcoes: list[str] | None = None,
    projetos: list[Projeto] | None = None,
) -> str:
    """Roda em paralelo com Habilidades: recebe as comportamentais da base, e não as
    escolhidas, para não precisar esperar aquele agente."""
    conteudo = {
        "experiencias": [
            {"cargo": x.cargo, "bullets": [b.texto for b in x.bullets]}
            for x in experiencias
        ],
        "projetos": [
            {"nome": p.nome, "bullets": [b.texto for b in p.bullets]}
            for p in projetos or []
        ],
        "cursos": [c.nome for c in cursos],
        "formacao": [f.curso for f in formacao],
        "qualidades_comportamentais": base.habilidades.behavioral,
    }
    saida = _chamar(
        llm,
        SaidaResumo,
        prompts.RESUMO.format(maximo=config.limites.resumo_palavras_max),
        f"Análise da vaga:\n{analise.model_dump_json(indent=1)}\n\n"
        f"Conteúdo selecionado:\n{_json(conteudo)}",
        correcoes,
    )
    return " ".join(saida.resumo.split())  # normaliza espaços e quebras de linha
