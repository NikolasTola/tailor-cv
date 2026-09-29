from pathlib import Path
from shutil import copytree

import pytest

from tailor_cv.carregadores import ErroDeOrigem, carregar_base
from tailor_cv.carregadores.origem import carregar_experiencia, carregar_idiomas

EXEMPLO = Path(__file__).parent.parent / "exemplos" / "dados"

CABECALHO = """---
id: teste
company: Teste
role: Dev
start: 2022-01
end: present
---

## Achievements
"""


@pytest.fixture
def base(tmp_path) -> Path:
    destino = tmp_path / "dados"
    copytree(EXEMPLO, destino)
    return destino


def _experiencia(tmp_path, conquistas: str, cabecalho: str = CABECALHO) -> Path:
    arquivo = tmp_path / "exp.md"
    arquivo.write_text(cabecalho + conquistas, encoding="utf-8")
    return arquivo


def test_base_de_exemplo_carrega():
    base = carregar_base(EXEMPLO)
    assert [x.id for x in base.experiencias] == ["empresa-alfa", "empresa-beta"]
    assert len(base.cursos) == 2  # _modelo.md é ignorado
    assert base.experiencias[0].end is None  # "present"
    assert (
        base.experiencias[0].achievements[1].metric
        == "30% reduction in monthly Bedrock spend"
    )
    assert "AWS Bedrock" in base.experiencias[0].achievements[0].tech


def test_bullet_completo(tmp_path):
    exp = carregar_experiencia(
        _experiencia(
            tmp_path, "- [a1] Did X.\n  - tech: Python, SQL\n  - metric: 10x\n"
        )
    )
    assert exp.achievements[0].tech == ["Python", "SQL"]
    assert exp.achievements[0].metric == "10x"


def test_bullet_sem_id(tmp_path):
    with pytest.raises(ErroDeOrigem, match="bullet sem ID"):
        carregar_experiencia(_experiencia(tmp_path, "- Did X without id\n"))


def test_id_de_bullet_repetido(tmp_path):
    with pytest.raises(ErroDeOrigem, match="repetidos"):
        carregar_experiencia(_experiencia(tmp_path, "- [a1] One.\n- [a1] Two.\n"))


def test_fim_antes_do_inicio(tmp_path):
    cab = CABECALHO.replace("end: present", "end: 2021-01")
    with pytest.raises(ErroDeOrigem, match="anterior"):
        carregar_experiencia(_experiencia(tmp_path, "- [a1] One.\n", cab))


def test_sem_conquistas(tmp_path):
    with pytest.raises(ErroDeOrigem, match="achievements"):
        carregar_experiencia(_experiencia(tmp_path, ""))


def test_nivel_de_idioma_invalido(tmp_path):
    arquivo = tmp_path / "idiomas.md"
    arquivo.write_text("- English: very good\n", encoding="utf-8")
    with pytest.raises(ErroDeOrigem, match="linha 1"):
        carregar_idiomas(arquivo)


def test_id_de_experiencia_repetido_entre_arquivos(base):
    original = base / "experiencias" / "empresa-beta.md"
    (base / "experiencias" / "copia.md").write_text(
        original.read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(ErroDeOrigem, match="IDs repetidos em experiencias"):
        carregar_base(base)


def test_arquivo_obrigatorio_faltando(base):
    (base / "perfil.yaml").unlink()
    with pytest.raises(ErroDeOrigem, match="perfil.yaml"):
        carregar_base(base)
