from pathlib import Path

import pytest
from llm_falsa import LLMFalsa

from tailor_cv.agentes import ErroDeRegra
from tailor_cv.agentes.analisador import analisar_vaga
from tailor_cv.agentes.experiencia import selecionar_experiencias
from tailor_cv.cache import ler_analise, salvar_analise
from tailor_cv.carregadores import carregar_base, carregar_i18n
from tailor_cv.config import carregar_config
from tailor_cv.grafo import construir_grafo
from tailor_cv.schemas import Curriculo
from tailor_cv.schemas.agentes import (
    AnaliseVaga,
    AvaliacaoExperiencia,
    BulletGerado,
    ExperienciaGerada,
    SaidaExperiencia,
)
from tailor_cv.validacao import validar_regras

RAIZ = Path(__file__).parent.parent
BASE = carregar_base(RAIZ / "exemplos" / "dados")
I18N = carregar_i18n(RAIZ / "i18n_pt.yaml")
CONFIG = carregar_config(RAIZ / "config.yaml")
VAGA = (RAIZ / "exemplos" / "vagas" / "vaga.exemplo.txt").read_text(encoding="utf-8")

ANALISE = AnaliseVaga(
    cargo="Engenheiro(a) de IA Pleno",
    senioridade="pleno",
    resumo_vaga="Aplicações de IA generativa em produção na AWS.",
    requisitos_obrigatorios=["Python", "LLMs e RAG", "AWS"],
    requisitos_desejaveis=["LangGraph", "OpenSearch"],
    palavras_chave=["Python", "RAG", "AWS Bedrock", "LangGraph"],
    headline="Engenheira de IA",
)


def _saida(nota_beta: int = 6, origem_extra: str | None = None) -> SaidaExperiencia:
    experiencias = [
        ExperienciaGerada(
            origem="empresa-beta",
            cargo="Analista de Dados",
            bullets=[
                BulletGerado(
                    origem=["beta-etl"],
                    texto="Construção de pipelines de dados em Python e SQL.",
                )
            ],
        ),
        ExperienciaGerada(
            origem="empresa-alfa",
            cargo="Engenheira de IA",
            bullets=[
                BulletGerado(
                    origem=["alfa-rag"],
                    texto="Desenvolvimento de chatbot RAG com AWS Bedrock, "
                    "utilizado por 2.000 colaboradores.",
                ),
                BulletGerado(
                    origem=["alfa-costs"],
                    texto="Governança de custos de LLMs, com redução de 30% no gasto.",
                ),
            ],
        ),
    ]
    if origem_extra:
        experiencias.append(
            ExperienciaGerada(
                origem=origem_extra,
                cargo="Inventado",
                bullets=[BulletGerado(origem=["x"], texto="Nada.")],
            )
        )
    return SaidaExperiencia(
        avaliacoes=[
            AvaliacaoExperiencia(
                origem="empresa-alfa", nota=9, justificativa="RAG na AWS."
            ),
            AvaliacaoExperiencia(
                origem="empresa-beta", nota=nota_beta, justificativa="Dados."
            ),
        ],
        experiencias=experiencias,
    )


# ---------- Analisador ----------


def test_analisador_envia_headlines_e_texto():
    llm = LLMFalsa(ANALISE)
    assert analisar_vaga(VAGA, BASE.perfil, llm) == ANALISE
    sistema, humano = llm.chamadas[0]
    assert "- Cloud Engineer" in sistema.content
    assert "Engenheiro(a) de IA Pleno" in humano.content


def test_analisador_com_headline_inventado():
    llm = LLMFalsa(ANALISE.model_copy(update={"headline": "Head de IA"}))
    with pytest.raises(ErroDeRegra, match="Head de IA"):
        analisar_vaga(VAGA, BASE.perfil, llm)


# ---------- Experiência ----------


def test_fatos_vem_da_origem_e_ordem_e_cronologica():
    experiencias, avaliacoes = selecionar_experiencias(
        ANALISE, BASE, CONFIG, I18N, LLMFalsa(_saida())
    )
    assert [x.origem for x in experiencias] == ["empresa-alfa", "empresa-beta"]
    alfa = experiencias[0]
    assert (alfa.empresa, alfa.inicio, alfa.fim, alfa.modalidade) == (
        "Empresa Alfa",
        "2023-03",
        None,
        "Híbrido",
    )
    assert len(avaliacoes) == 2


def test_experiencia_abaixo_do_corte_e_omitida():
    experiencias, _ = selecionar_experiencias(
        ANALISE, BASE, CONFIG, I18N, LLMFalsa(_saida(nota_beta=2))
    )
    assert [x.origem for x in experiencias] == ["empresa-alfa"]


def test_always_include_entra_mesmo_com_nota_baixa():
    saida = _saida()
    saida.avaliacoes[0].nota = 1  # empresa-alfa tem always_include: true
    experiencias, _ = selecionar_experiencias(
        ANALISE, BASE, CONFIG, I18N, LLMFalsa(saida)
    )
    assert "empresa-alfa" in [x.origem for x in experiencias]


def test_experiencia_com_id_inventado_e_descartada():
    experiencias, _ = selecionar_experiencias(
        ANALISE, BASE, CONFIG, I18N, LLMFalsa(_saida(origem_extra="empresa-fantasma"))
    )
    assert "empresa-fantasma" not in [x.origem for x in experiencias]


def test_saida_do_agente_passa_no_validador_de_regras():
    experiencias, _ = selecionar_experiencias(
        ANALISE, BASE, CONFIG, I18N, LLMFalsa(_saida())
    )
    cv = Curriculo.model_validate_json(
        (RAIZ / "exemplos" / "curriculo.exemplo.json").read_text(encoding="utf-8")
    )
    cv.experiencias = experiencias
    resultado = validar_regras(cv, BASE, I18N, CONFIG)
    assert resultado.aprovado, resultado.bloqueios


# ---------- Grafo ----------


def test_grafo_roda_analisador_e_experiencia():
    llms = {"analisador": LLMFalsa(ANALISE), "experiencia": LLMFalsa(_saida())}
    estado = construir_grafo(BASE, CONFIG, I18N, llms).invoke({"texto_vaga": VAGA})
    assert estado["analise"].headline == "Engenheira de IA"
    assert len(estado["experiencias"]) == 2


def test_grafo_pula_analisador_com_analise_em_cache():
    analisador = LLMFalsa(ANALISE)
    llms = {"analisador": analisador, "experiencia": LLMFalsa(_saida())}
    grafo = construir_grafo(BASE, CONFIG, I18N, llms)
    grafo.invoke({"texto_vaga": VAGA, "analise": ANALISE})
    assert analisador.chamadas == []


# ---------- Cache ----------


def test_cache_da_analise(tmp_path):
    assert ler_analise("vaga", VAGA, BASE.perfil, tmp_path) is None
    salvar_analise("vaga", VAGA, ANALISE, tmp_path)
    assert ler_analise("vaga", VAGA, BASE.perfil, tmp_path) == ANALISE
    # vaga editada: cache inválido
    assert ler_analise("vaga", VAGA + " ", BASE.perfil, tmp_path) is None


def test_cache_ignorado_se_headline_saiu_da_lista(tmp_path):
    salvar_analise("vaga", VAGA, ANALISE, tmp_path)
    perfil = BASE.perfil.model_copy(update={"headlines": ["Cloud Engineer"]})
    assert ler_analise("vaga", VAGA, perfil, tmp_path) is None
