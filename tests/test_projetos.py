"""Seção Projetos: leitura, validação de regras e de fidelidade, PDF e corte."""

from pathlib import Path

import pytest
from llm_falsa import LLMFalsa
from test_agentes_llm import ANALISE
from test_agentes_secoes import PROJETOS

from tailor_cv.agentes.secoes import selecionar_projetos
from tailor_cv.carregadores import ErroDeOrigem, carregar_base, carregar_i18n
from tailor_cv.carregadores.origem import carregar_projeto
from tailor_cv.config import carregar_config
from tailor_cv.render import ajustar_paginas, gerar_pdf
from tailor_cv.schemas import Curriculo
from tailor_cv.schemas.agentes import SaidaFidelidade
from tailor_cv.validacao import validar_fidelidade, validar_regras

RAIZ = Path(__file__).parent.parent
BASE = carregar_base(RAIZ / "exemplos" / "dados")
I18N = carregar_i18n(RAIZ / "i18n_pt.yaml")
CONFIG = carregar_config(RAIZ / "config.yaml")
JSON = (RAIZ / "exemplos" / "curriculo.exemplo.json").read_text(encoding="utf-8")


@pytest.fixture
def cv() -> Curriculo:
    cv = Curriculo.model_validate_json(JSON)
    cv.projetos = selecionar_projetos(ANALISE, BASE, CONFIG, LLMFalsa(PROJETOS))
    return cv


def _verificacoes(cv: Curriculo) -> set[str]:
    return {p.verificacao for p in validar_regras(cv, BASE, I18N, CONFIG).bloqueios}


def test_projeto_de_exemplo_carrega():
    [p] = BASE.projetos
    assert (p.id, p.type, p.year, p.award) == (
        "assistente-rag",
        "academic",
        2025,
        "Best final project of the course",
    )
    assert p.achievements[0].tech == ["Python", "LangGraph", "RAG"]


def test_projeto_sem_bullets_e_rejeitado(tmp_path):
    arquivo = tmp_path / "p.md"
    arquivo.write_text("---\nid: vazio\nname: Empty\n---\n", encoding="utf-8")
    with pytest.raises(ErroDeOrigem, match="achievements"):
        carregar_projeto(arquivo)


def test_curriculo_com_projeto_passa_nas_regras(cv):
    assert validar_regras(cv, BASE, I18N, CONFIG).aprovado


def test_ano_e_link_divergentes(cv):
    cv.projetos[0].ano = "2024"
    cv.projetos[0].url = "github.com/outro"
    assert "divergente" in _verificacoes(cv)


def test_reconhecimento_sem_award_na_origem(cv):
    base = BASE.model_copy(
        update={"projetos": [BASE.projetos[0].model_copy(update={"award": None})]}
    )
    bloqueios = validar_regras(cv, base, I18N, CONFIG).bloqueios
    assert "reconhecimento_sem_origem" in {p.verificacao for p in bloqueios}


def test_bullet_de_projeto_com_numero_e_tecnologia_sem_lastro(cv):
    cv.projetos[0].bullets[
        0
    ].texto = "Assistente RAG com OpenSearch usado por 300 alunos."
    verificacoes = _verificacoes(cv)
    assert {"numero_sem_origem", "tecnologia_sem_lastro"} <= verificacoes


def test_projeto_inexistente(cv):
    cv.projetos[0].origem = "fantasma"
    assert "origem_inexistente" in _verificacoes(cv)


def test_resumo_pode_citar_tecnologia_do_projeto(cv):
    cv.resumo = "Profissional com experiência em RAG e LangGraph na AWS."
    assert validar_regras(cv, BASE, I18N, CONFIG).aprovado


def test_fidelidade_recebe_itens_do_projeto(cv):
    llm = LLMFalsa(SaidaFidelidade(avaliacoes=[]))
    validar_fidelidade(cv, BASE, llm)
    humano = llm.chamadas[0][1].content
    for item in ("nome", "reconhecimento", "bullet:0"):
        assert f'"id": "projeto:assistente-rag:{item}"' in humano
    assert "Best final project of the course" in humano


def test_pdf_tem_secao_de_projetos(cv, tmp_path):
    from reportlab.platypus import KeepTogether, Paragraph

    from tailor_cv.render.pdf import _montar

    def textos(flowables):
        for f in flowables:
            if isinstance(f, KeepTogether):
                yield from textos(f._content)
            elif isinstance(f, Paragraph):
                yield f.getPlainText()

    conteudo = list(textos(_montar(cv)))
    assert "PROJETOS" in conteudo
    assert any("Melhor projeto final do curso" in t and "(2025)" in t for t in conteudo)
    assert gerar_pdf(cv, tmp_path / "cv.pdf") >= 1


def test_corte_remove_projetos_depois_dos_cursos(cv):
    for x in cv.experiencias:  # infla o currículo para passar de 1 página
        x.bullets = x.bullets * 12
    _, _, cortes = ajustar_paginas(cv, 1, {"empresa-alfa": 9, "empresa-beta": 5})
    tipos = [c.split(":")[0] for c in cortes]
    assert tipos[:3] == ["curso removido", "curso removido", "projeto removido"]
