import json
import shutil
from pathlib import Path

from llm_falsa import LLMFalsa
from test_agentes_llm import ANALISE, _saida
from typer.testing import CliRunner

from tailor_cv import cli

RAIZ = Path(__file__).parent.parent
ARGS = [
    "json",
    "--vaga",
    "exemplos/vagas/vaga.exemplo.txt",
    "--dados",
    "exemplos/dados",
]


def test_comando_json_salva_resultados_parciais_e_usa_cache(tmp_path, monkeypatch):
    for nome in ("config.yaml", "i18n_pt.yaml"):
        shutil.copy(RAIZ / nome, tmp_path / nome)
    shutil.copytree(RAIZ / "exemplos", tmp_path / "exemplos")
    monkeypatch.chdir(tmp_path)

    # uma LLM falsa responde aos dois agentes: ela escolhe a resposta pelo schema
    llm = LLMFalsa(ANALISE, _saida())
    monkeypatch.setattr(cli, "criar_llm", lambda _modelo: llm)

    resultado = CliRunner().invoke(cli.app, ARGS)
    assert resultado.exit_code == 0, resultado.output
    assert "headline: Engenheira de IA" in resultado.output

    execucao = next(p for p in (tmp_path / "execucoes").iterdir() if p.name != "cache")
    parcial = json.loads((execucao / "experiencias.json").read_text(encoding="utf-8"))
    assert [x["origem"] for x in parcial["experiencias"]] == [
        "empresa-alfa",
        "empresa-beta",
    ]

    chamadas_antes = len(llm.chamadas)
    resultado = CliRunner().invoke(cli.app, ARGS)
    assert "em cache" in resultado.output
    assert len(llm.chamadas) == chamadas_antes + 1  # só a Experiência rodou de novo
