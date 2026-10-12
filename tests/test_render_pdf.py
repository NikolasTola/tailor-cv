from pathlib import Path

import pytest

from tailor_cv.render.pdf import data_pt, gerar_pdf
from tailor_cv.schemas import Curriculo

EXEMPLO = Path(__file__).parent.parent / "exemplos" / "curriculo.exemplo.json"


@pytest.mark.parametrize(
    ("entrada", "saida"),
    [("2021-01", "Jan/2021"), ("2019-12", "Dez/2019"), (None, "Atual")],
)
def test_data_pt(entrada, saida):
    assert data_pt(entrada) == saida


def test_gera_pdf(tmp_path):
    cv = Curriculo.model_validate_json(EXEMPLO.read_text(encoding="utf-8"))
    destino = tmp_path / "curriculo.exemplo.pdf"
    paginas = gerar_pdf(cv, destino)
    assert destino.read_bytes().startswith(b"%PDF")
    assert paginas == 1


def test_escapa_caracteres_especiais(tmp_path):
    # "&" e "<" quebrariam o markup do ReportLab se não fossem escapados
    cv = Curriculo.model_validate_json(EXEMPLO.read_text(encoding="utf-8"))
    cv.experiencias[0].bullets[0].texto = "Uso de P&D e métricas <10ms"
    assert gerar_pdf(cv, tmp_path / "x.pdf") >= 1


@pytest.mark.parametrize(
    ("entrada", "saida"),
    [
        ("e\u2011commerce", "e-commerce"),  # hífen sem quebra, comum em LLMs
        ("pré\u2010processamento", "pré-processamento"),
        ("100\u202fms", "100 ms"),
        ("travessão — e “aspas”", "travessão — e “aspas”"),  # já suportados
        ("ação, coração", "ação, coração"),
    ],
)
def test_texto_seguro_para_helvetica(entrada, saida):
    from tailor_cv.render.pdf import texto_seguro

    assert texto_seguro(entrada) == saida
    texto_seguro(entrada).encode("cp1252")  # nada fora da tabela da fonte


def test_titulo_de_secao_nunca_fica_sozinho_no_fim_da_pagina():
    from reportlab.platypus import KeepTogether

    from tailor_cv.render.pdf import _montar

    cv = Curriculo.model_validate_json(EXEMPLO.read_text(encoding="utf-8"))
    for bloco in _montar(cv):
        if isinstance(bloco, KeepTogether):
            conteudo = bloco._content
            if type(conteudo[-1]).__name__ == "HRFlowable":
                raise AssertionError("título de seção sem o primeiro item junto")
            assert not any(isinstance(c, KeepTogether) for c in conteudo)
