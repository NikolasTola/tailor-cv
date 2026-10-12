from pathlib import Path

import pytest
from llm_falsa import LLMFalsa
from test_agentes_llm import ANALISE, _saida
from test_agentes_secoes import RESUMO

from tailor_cv.agentes.experiencia import selecionar_experiencias
from tailor_cv.agentes.prompts import HABILIDADES
from tailor_cv.agentes.prompts import RESUMO as PROMPT_RESUMO
from tailor_cv.agentes.secoes import escrever_resumo
from tailor_cv.carregadores import ErroDeOrigem, carregar_base, carregar_i18n
from tailor_cv.carregadores.origem import carregar_posicionamento
from tailor_cv.config import carregar_config
from tailor_cv.schemas import Curriculo
from tailor_cv.validacao import validar_regras

RAIZ = Path(__file__).parent.parent
BASE = carregar_base(RAIZ / "exemplos" / "dados")
I18N = carregar_i18n(RAIZ / "i18n_pt.yaml")
CONFIG = carregar_config(RAIZ / "config.yaml")


def test_posicionamento_de_exemplo_carrega():
    assert BASE.posicionamento[0].startswith("Builds technology solutions")


def test_linha_fora_do_formato(tmp_path):
    arquivo = tmp_path / "posicionamento.md"
    arquivo.write_text("Frase sem hífen\n", encoding="utf-8")
    with pytest.raises(ErroDeOrigem, match="linha 1"):
        carregar_posicionamento(arquivo)


def test_resumo_recebe_o_posicionamento():
    experiencias = selecionar_experiencias(
        ANALISE, BASE, CONFIG, I18N, LLMFalsa(_saida())
    )[0]
    llm = LLMFalsa(RESUMO)
    escrever_resumo(ANALISE, experiencias, [], [], BASE, CONFIG, llm)
    assert "with or without AI" in llm.chamadas[0][1].content


def test_regras_aceitam_resumo_baseado_no_posicionamento():
    cv = Curriculo.model_validate_json(
        (RAIZ / "exemplos" / "curriculo.exemplo.json").read_text(encoding="utf-8")
    )
    cv.resumo = (
        "Engenheira de IA com experiência em RAG na AWS. Desenvolve soluções de "
        "tecnologia, com ou sem IA, para resolver problemas de negócio."
    )
    assert validar_regras(cv, BASE, I18N, CONFIG).aprovado


def test_prompts_tratam_o_genero_pelo_headline():
    assert "gênero gramatical do headline" in HABILIDADES
    assert "gênero gramatical do headline" in PROMPT_RESUMO
    assert "candidata," not in HABILIDADES and "da candidata" not in PROMPT_RESUMO
