from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="TailorCV: currículo sob medida para cada vaga.")

VagaOpt = Annotated[Path, typer.Option("--vaga", help="Arquivo .txt da vaga")]


@app.command("json")
def gerar_json(vaga: VagaOpt) -> None:
    """Roda os agentes e gera curriculos/curriculo.<nome_vaga>.json."""
    typer.echo(f"[em construção] json para {vaga.stem}")


@app.command("pdf")
def gerar_pdf(
    arquivo: Annotated[Path, typer.Argument(help="Arquivo curriculo.<nome_vaga>.json")],
) -> None:
    """Gera o PDF a partir de um curriculo.<nome_vaga>.json."""
    typer.echo(f"[em construção] pdf de {arquivo}")


@app.command("gerar")
def gerar(vaga: VagaOpt) -> None:
    """Gera o JSON e depois o PDF."""
    typer.echo(f"[em construção] json + pdf para {vaga.stem}")