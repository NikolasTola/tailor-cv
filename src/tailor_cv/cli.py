from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from tailor_cv.carregadores import ErroDeOrigem, carregar_base
from tailor_cv.render import gerar_pdf
from tailor_cv.schemas import Curriculo

app = typer.Typer(help="TailorCV: currículo sob medida para cada vaga.")

VagaOpt = Annotated[Path, typer.Option("--vaga", help="Arquivo .txt da vaga")]
DadosOpt = Annotated[
    Path, typer.Option("--dados", help="Pasta da base de dados pessoal")
]


def _erro(mensagem: str) -> NoReturn:
    typer.secho(mensagem, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


@app.command("json")
def gerar_json(vaga: VagaOpt) -> None:
    """Roda os agentes e gera curriculos/curriculo.<nome_vaga>.json."""
    typer.echo(f"[em construção] json para {vaga.stem}")


@app.command("pdf")
def gerar_pdf_cmd(
    arquivo: Annotated[Path, typer.Argument(help="Arquivo curriculo.<nome_vaga>.json")],
) -> None:
    """Gera o PDF a partir de um curriculo.<nome_vaga>.json."""
    if not arquivo.is_file():
        _erro(f"Arquivo não encontrado: {arquivo}")
    try:
        cv = Curriculo.model_validate_json(arquivo.read_text(encoding="utf-8"))
    except ValidationError as exc:
        linhas = [
            f"  - {'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        ]
        _erro(f"{arquivo} não segue o formato do currículo:\n" + "\n".join(linhas))

    destino = arquivo.with_suffix(".pdf")
    paginas = gerar_pdf(cv, destino)
    typer.secho(f"PDF gerado: {destino} ({paginas} página(s))", fg=typer.colors.GREEN)


@app.command("gerar")
def gerar(vaga: VagaOpt) -> None:
    """Gera o JSON e depois o PDF."""
    typer.echo(f"[em construção] json + pdf para {vaga.stem}")


@app.command("checar")
def checar(dados: DadosOpt = Path("dados")) -> None:
    """Lê a base de dados e aponta problemas nos arquivos, sem chamar nenhuma LLM."""
    try:
        base = carregar_base(dados)
    except ErroDeOrigem as exc:
        _erro(f"Problema na base de dados:\n  {exc}")

    bullets = sum(len(x.achievements) for x in base.experiencias)
    com_metrica = sum(1 for x in base.experiencias for a in x.achievements if a.metric)
    hab = base.habilidades
    typer.secho(f"Base de dados OK: {dados}", fg=typer.colors.GREEN)
    typer.echo(
        f"  Experiências: {len(base.experiencias)} ({bullets} bullets, {com_metrica} com métrica)"
    )
    typer.echo(f"  Formação:     {len(base.formacao)}")
    typer.echo(f"  Cursos:       {len(base.cursos)}")
    typer.echo(
        f"  Habilidades:  {len(hab.technical)} técnicas, {len(hab.behavioral)} comportamentais"
    )
    typer.echo(f"  Idiomas:      {len(base.idiomas)}")
    typer.echo(f"  Headlines:    {', '.join(base.perfil.headlines)}")
