from pathlib import Path

import pytest

from tailor_cv.agentes import (
    ErroDeRegra,
    dados_pessoais,
    idiomas,
    modalidade,
    titulo_e_nome,
)
from tailor_cv.carregadores import ErroDeOrigem, carregar_base, carregar_i18n
from tailor_cv.schemas.curriculo import Cabecalho
from tailor_cv.schemas.origem import IdiomaOrigem

RAIZ = Path(__file__).parent.parent
BASE = carregar_base(RAIZ / "exemplos" / "dados")
I18N = carregar_i18n(RAIZ / "i18n_pt.yaml")


def test_titulo_e_nome_com_headline_aprovado():
    assert titulo_e_nome(BASE.perfil, "Cloud Engineer") == {
        "nome": "Maria Exemplo da Silva",
        "headline": "Cloud Engineer",
    }


def test_headline_fora_da_lista_e_rejeitado():
    with pytest.raises(ErroDeRegra, match="lista aprovada"):
        titulo_e_nome(BASE.perfil, "Diretora de Tecnologia")


def test_cabecalho_completo_valida_no_schema_do_curriculo():
    cab = Cabecalho(
        **titulo_e_nome(BASE.perfil, "Engenheira de IA"),
        **dados_pessoais(BASE.perfil),
    )
    assert cab.github == "github.com/maria-exemplo"


def test_idiomas_traduzidos_na_ordem_do_arquivo():
    resultado = idiomas(BASE.idiomas, I18N)
    assert [(i.idioma, i.nivel) for i in resultado] == [
        ("Português", "Nativo"),
        ("Inglês", "Avançado"),
    ]


def test_idioma_sem_traducao():
    lista = [IdiomaOrigem(language="Klingon", level="basic")]
    with pytest.raises(ErroDeRegra, match="Klingon"):
        idiomas(lista, I18N)


@pytest.mark.parametrize(
    ("entrada", "saida"),
    [
        ("remote", "Remoto"),
        ("hybrid", "Híbrido"),
        ("onsite", "Presencial"),
        (None, None),
    ],
)
def test_modalidade(entrada, saida):
    assert modalidade(entrada, I18N) == saida


def test_i18n_sem_um_nivel(tmp_path):
    arquivo = tmp_path / "i18n.yaml"
    texto = (RAIZ / "i18n_pt.yaml").read_text(encoding="utf-8")
    arquivo.write_text(texto.replace("  basic: Básico\n", ""), encoding="utf-8")
    with pytest.raises(ErroDeOrigem, match="basic"):
        carregar_i18n(arquivo)
