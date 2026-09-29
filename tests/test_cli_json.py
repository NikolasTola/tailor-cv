import json
import shutil
from pathlib import Path

import pytest
from llm_falsa import LLMFalsa
from test_agentes_llm import ANALISE, _saida
from test_agentes_secoes import CURSOS, FORMACAO, HABILIDADES, RESUMO
from typer.testing import CliRunner

from tailor_cv import cli

RAIZ = Path(__file__).parent.parent
VAGA = ["--vaga", "exemplos/vagas/vaga.exemplo.txt", "--dados", "exemplos/dados"]


@pytest.fixture
def projeto(tmp_path, monkeypatch) -> tuple[Path, LLMFalsa]:
    for nome in ("config.yaml", "i18n_pt.yaml"):
        shutil.copy(RAIZ / nome, tmp_path / nome)
    shutil.copytree(RAIZ / "exemplos", tmp_path / "exemplos")
    monkeypatch.chdir(tmp_path)
    llm = LLMFalsa(ANALISE, _saida(), FORMACAO, CURSOS, HABILIDADES, RESUMO)
    monkeypatch.setattr(cli, "criar_llm", lambda _modelo: llm)
    return tmp_path, llm


def test_json_gera_curriculo_relatorio_e_usa_cache(projeto):
    raiz, llm = projeto
    resultado = CliRunner().invoke(cli.app, ["json", *VAGA])
    assert resultado.exit_code == 0, resultado.output

    curriculo = raiz / "curriculos" / "curriculo.vaga.exemplo.json"
    dados = json.loads(curriculo.read_text(encoding="utf-8"))
    assert dados["cabecalho"]["headline"] == "Engenheira de IA"

    execucao = next(p for p in (raiz / "execucoes").iterdir() if p.name != "cache")
    relatorio = (execucao / "relatorio.md").read_text(encoding="utf-8")
    assert "| 9 | incluída | empresa-alfa |" in relatorio

    chamadas = len(llm.chamadas)
    CliRunner().invoke(cli.app, ["json", *VAGA])
    assert len(llm.chamadas) == chamadas + 5  # todos menos o Analisador (cache)


def test_gerar_cria_json_e_pdf(projeto):
    raiz, _ = projeto
    resultado = CliRunner().invoke(cli.app, ["gerar", *VAGA])
    assert resultado.exit_code == 0, resultado.output
    pdf = raiz / "curriculos" / "curriculo.vaga.exemplo.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")


def test_json_reprovado_nas_regras_nao_gera_curriculo(projeto):
    raiz, llm = projeto
    llm.respostas[type(RESUMO)] = RESUMO.model_copy(
        update={"resumo": "Profissional com 10 anos de experiência em AWS."}
    )
    resultado = CliRunner().invoke(cli.app, ["json", *VAGA])
    assert resultado.exit_code == 1
    assert "numero_sem_origem" not in resultado.output  # mensagem é legível
    assert "10" in resultado.output
    assert not (raiz / "curriculos").exists()
