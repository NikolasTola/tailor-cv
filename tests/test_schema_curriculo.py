import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tailor_cv.schemas import Curriculo

EXEMPLO = Path(__file__).parent.parent / "exemplos" / "curriculo.exemplo.json"


def _exemplo() -> dict:
    return json.loads(EXEMPLO.read_text(encoding="utf-8"))


def test_exemplo_e_valido():
    cv = Curriculo.model_validate(_exemplo())
    assert cv.cabecalho.nome == "Maria Exemplo da Silva"


@pytest.mark.parametrize("data", ["2021-13", "2021-1", "01/2021", "2021"])
def test_data_invalida(data):
    d = _exemplo()
    d["experiencias"][0]["inicio"] = data
    with pytest.raises(ValidationError):
        Curriculo.model_validate(d)


def test_fim_antes_do_inicio():
    d = _exemplo()
    d["experiencias"][1]["inicio"], d["experiencias"][1]["fim"] = "2023-02", "2020-01"
    with pytest.raises(ValidationError, match="anterior ao início"):
        Curriculo.model_validate(d)


def test_campo_desconhecido_e_rejeitado():
    d = _exemplo()
    d["cabecalho"]["linkdin"] = "erro de digitação"
    with pytest.raises(ValidationError):
        Curriculo.model_validate(d)


def test_experiencia_sem_bullets():
    d = _exemplo()
    d["experiencias"][0]["bullets"] = []
    with pytest.raises(ValidationError):
        Curriculo.model_validate(d)


def test_origem_do_bullet_aceita_texto_ou_lista():
    d = _exemplo()
    d["experiencias"][0]["bullets"][0]["origem"] = "alfa-rag"
    d["experiencias"][0]["bullets"][1]["origem"] = ["alfa-rag", "alfa-costs"]
    cv = Curriculo.model_validate(d)
    assert cv.experiencias[0].bullets[0].origem == ["alfa-rag"]
    assert cv.experiencias[0].bullets[1].origem == ["alfa-rag", "alfa-costs"]
