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
