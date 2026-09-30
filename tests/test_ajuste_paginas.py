from pathlib import Path

from tailor_cv.render import ajustar_paginas
from tailor_cv.schemas import Curriculo
from tailor_cv.schemas.curriculo import Bullet

RAIZ = Path(__file__).parent.parent
CV = Curriculo.model_validate_json(
    (RAIZ / "exemplos" / "curriculo.exemplo.json").read_text(encoding="utf-8")
)
NOTAS = {"empresa-alfa": 9, "empresa-beta": 5}


def _inchado(bullets_por_experiencia: int) -> Curriculo:
    cv = CV.model_copy(deep=True)
    for x in cv.experiencias:
        modelo = x.bullets[0]
        x.bullets = [
            Bullet(origem=modelo.origem, texto=f"{modelo.texto} ({i})")
            for i in range(bullets_por_experiencia)
        ]
    return cv


def test_curriculo_que_cabe_nao_e_cortado():
    cv, paginas, cortes = ajustar_paginas(CV, 2, NOTAS)
    assert (paginas, cortes) == (1, [])
    assert cv == CV


def test_corta_cursos_antes_de_bullets():
    cv, paginas, cortes = ajustar_paginas(_inchado(14), 1, NOTAS)
    assert cortes[0].startswith(
        "curso removido: LangGraph"
    )  # o último da lista sai primeiro
    assert cortes[1].startswith("curso removido: AWS")
    assert cv.cursos == []
    assert paginas == 1


def test_bullets_saem_da_experiencia_de_menor_nota():
    cv, _, cortes = ajustar_paginas(_inchado(14), 1, NOTAS)
    bullets_cortados = [c for c in cortes if c.startswith("bullet")]
    assert bullets_cortados and all("Empresa Beta" in c for c in bullets_cortados[:3])
    alfa = next(x for x in cv.experiencias if x.origem == "empresa-alfa")
    beta = next(x for x in cv.experiencias if x.origem == "empresa-beta")
    assert len(alfa.bullets) >= len(beta.bullets)


def test_nunca_remove_o_ultimo_bullet_nem_altera_o_original():
    cv, _, _ = ajustar_paginas(_inchado(60), 1, NOTAS)
    assert all(len(x.bullets) >= 1 for x in cv.experiencias)
    assert len(CV.experiencias[0].bullets) == 3  # o original não foi modificado
