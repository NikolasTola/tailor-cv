from pathlib import Path

import pytest

from tailor_cv.carregadores import carregar_base, carregar_i18n
from tailor_cv.config import carregar_config
from tailor_cv.schemas import Curriculo
from tailor_cv.validacao import validar_regras
from tailor_cv.validacao.regras import numeros_en, numeros_pt

RAIZ = Path(__file__).parent.parent
BASE = carregar_base(RAIZ / "exemplos" / "dados")
I18N = carregar_i18n(RAIZ / "i18n_pt.yaml")
CONFIG = carregar_config(RAIZ / "config.yaml")
JSON = (RAIZ / "exemplos" / "curriculo.exemplo.json").read_text(encoding="utf-8")


@pytest.fixture
def cv() -> Curriculo:
    return Curriculo.model_validate_json(JSON)


def _validar(cv: Curriculo):
    return validar_regras(cv, BASE, I18N, CONFIG)


def _verificacoes(problemas) -> set[str]:
    return {p.verificacao for p in problemas}


# ---------- números ----------


@pytest.mark.parametrize(
    ("pt", "en"),
    [
        ("2.000 colaboradores", "2,000 employees"),
        ("redução de 2,5x", "2.5x reduction"),
        ("30% do gasto", "30% of spend"),
        ("de 2 h para 15 min", "from 2 h to 15 min"),
        ("Python 3.12", "Python 3.12"),
    ],
)
def test_mesmo_numero_em_pt_e_en(pt, en):
    assert numeros_pt(pt) == numeros_en(en)


def test_numeros_colados_em_letras_sao_ignorados():
    assert numeros_pt("serviços S3 e EC2") == set()


# ---------- currículo válido ----------


def test_exemplo_passa_sem_bloqueios(cv):
    resultado = _validar(cv)
    assert resultado.aprovado, resultado.bloqueios
    assert resultado.alertas == []


def test_bullet_que_funde_dois_bullets_de_origem(cv):
    cv.experiencias[0].bullets[0].origem = ["alfa-rag", "alfa-costs"]
    cv.experiencias[0].bullets[0].texto = (
        "Chatbot RAG com AWS Bedrock usado por 2.000 colaboradores, "
        "com redução de 30% no gasto."
    )
    assert _validar(cv).aprovado


# ---------- bloqueios ----------


def test_numero_inventado(cv):
    cv.experiencias[0].bullets[
        0
    ].texto = "Chatbot RAG utilizado por 3.000 colaboradores."
    resultado = _validar(cv)
    assert "numero_sem_origem" in _verificacoes(resultado.bloqueios)
    assert resultado.bloqueios[0].agente == "experiencia"


def test_tecnologia_sem_lastro(cv):
    cv.experiencias[1].bullets[0].texto = "Pipelines de dados em Python com LangGraph."
    problemas = _validar(cv).bloqueios
    assert "tecnologia_sem_lastro" in _verificacoes(problemas)
    assert "LangGraph" in problemas[0].mensagem


def test_bullet_com_origem_inexistente(cv):
    cv.experiencias[0].bullets[0].origem = ["nao-existe"]
    assert "bullet_sem_origem" in _verificacoes(_validar(cv).bloqueios)


def test_bullet_de_outra_experiencia(cv):
    cv.experiencias[0].bullets[0].origem = ["beta-etl"]
    assert "bullet_sem_origem" in _verificacoes(_validar(cv).bloqueios)


def test_datas_e_empresa_divergentes(cv):
    cv.experiencias[1].inicio = "2019-01"
    cv.experiencias[1].empresa = "Empresa Gama"
    bloqueios = _validar(cv).bloqueios
    assert len([p for p in bloqueios if p.verificacao == "divergente"]) == 2


def test_modalidade_divergente(cv):
    cv.experiencias[1].modalidade = "Presencial"
    assert "divergente" in _verificacoes(_validar(cv).bloqueios)


def test_experiencia_obrigatoria_omitida(cv):
    cv.experiencias = cv.experiencias[1:]  # remove empresa-alfa (always_include)
    assert "obrigatoria_omitida" in _verificacoes(_validar(cv).bloqueios)


def test_headline_fora_da_lista(cv):
    cv.cabecalho.headline = "Diretora de Tecnologia"
    assert "headline_fora_da_lista" in _verificacoes(_validar(cv).bloqueios)


def test_contato_divergente(cv):
    cv.cabecalho.telefone = "(31) 99999-9999"
    bloqueios = _validar(cv).bloqueios
    assert [p.agente for p in bloqueios] == ["dados_pessoais"]


def test_habilidade_fora_da_base(cv):
    cv.habilidades.append(cv.habilidades[0].model_copy(update={"origem": "Kubernetes"}))
    assert "fora_da_base" in _verificacoes(_validar(cv).bloqueios)


def test_curso_com_ano_divergente(cv):
    cv.cursos[0].ano = "2020"
    assert "divergente" in _verificacoes(_validar(cv).bloqueios)


def test_palavra_proibida_no_resumo(cv):
    cv.resumo = "Profissional apaixonada por dados e IA generativa em nuvem AWS."
    assert "palavra_proibida" in _verificacoes(_validar(cv).bloqueios)


def test_numero_inventado_no_resumo(cv):
    cv.resumo = "Profissional com 10 anos de experiência em dados na AWS."
    problemas = _validar(cv).bloqueios
    assert [(p.agente, p.verificacao) for p in problemas] == [
        ("resumo", "numero_sem_origem")
    ]


def test_idiomas_divergentes(cv):
    cv.idiomas[1].nivel = "Fluente"
    assert "divergente" in _verificacoes(_validar(cv).bloqueios)


# ---------- alertas ----------


def test_bullet_longo_gera_alerta(cv):
    cv.experiencias[1].bullets[0].texto = " ".join(["dados"] * 30)
    resultado = _validar(cv)
    assert resultado.aprovado
    assert "texto_longo" in _verificacoes(resultado.alertas)


def test_habilidade_tecnica_traduzida_gera_alerta(cv):
    cv.habilidades[0].texto = "Píton"
    resultado = _validar(cv)
    assert resultado.aprovado
    assert "termo_traduzido" in _verificacoes(resultado.alertas)
