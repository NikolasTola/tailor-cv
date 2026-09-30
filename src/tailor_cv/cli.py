from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from dotenv import load_dotenv
from pydantic import ValidationError
from rich.console import Console
from rich.live import Live

from tailor_cv.agentes import ErroDeRegra
from tailor_cv.cache import ler_analise, salvar_analise
from tailor_cv.carregadores import ErroDeOrigem, carregar_base, carregar_i18n
from tailor_cv.config import carregar_config
from tailor_cv.grafo import construir_grafo
from tailor_cv.llm import criar_llm, descrever_erro
from tailor_cv.painel import Painel
from tailor_cv.relatorio import gerar_relatorio
from tailor_cv.render import ajustar_paginas, gerar_pdf
from tailor_cv.schemas import Curriculo
from tailor_cv.validacao import validar_fidelidade, validar_regras

app = typer.Typer(help="TailorCV: currículo sob medida para cada vaga.")
console = Console()

VagaOpt = Annotated[Path, typer.Option("--vaga", help="Arquivo .txt da vaga")]
DadosOpt = Annotated[
    Path, typer.Option("--dados", help="Pasta da base de dados pessoal")
]
PASTA_CURRICULOS = Path("curriculos")
AGENTES_LLM = (
    "analisador",
    "experiencia",
    "formacao",
    "cursos",
    "habilidades",
    "resumo",
    "validador",
    "projetos",
)


def _erro(mensagem: str) -> NoReturn:
    typer.secho(mensagem, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _ler_curriculo(arquivo: Path) -> Curriculo:
    if not arquivo.is_file():
        _erro(f"Arquivo não encontrado: {arquivo}")
    try:
        return Curriculo.model_validate_json(arquivo.read_text(encoding="utf-8"))
    except ValidationError as exc:
        linhas = [
            f"  - {'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        ]
        _erro(f"{arquivo} não segue o formato do currículo:\n" + "\n".join(linhas))


def _carregar_tudo(dados: Path) -> tuple[Any, Any, Any]:
    try:
        return carregar_base(dados), carregar_i18n(), carregar_config()
    except ErroDeOrigem as exc:
        _erro(f"Problema ao carregar a base ou a configuração:\n  {exc}")


def _executar_json(vaga: Path, dados: Path) -> Path:
    """Roda o grafo completo e devolve o caminho do curriculo.<nome_vaga>.json."""
    load_dotenv()
    if not vaga.is_file():
        _erro(f"Arquivo da vaga não encontrado: {vaga}")
    texto_vaga = vaga.read_text(encoding="utf-8")
    nome_vaga = vaga.stem
    base, i18n, config = _carregar_tudo(dados)

    analise = ler_analise(nome_vaga, texto_vaga, base.perfil)
    entrada: dict[str, Any] = {"texto_vaga": texto_vaga}
    if analise:
        entrada["analise"] = analise

    painel = Painel()
    estado: dict[str, Any] = dict(entrada)
    try:
        # um modelo por agente, como definido no config.yaml
        # Projetos usa o modelo de Cursos se o config.yaml não definir um próprio
        modelos = config.modelos.model_dump()
        modelos["projetos"] = modelos["projetos"] or modelos["cursos"]
        llms = {nome: criar_llm(modelos[nome]) for nome in AGENTES_LLM}
        grafo = construir_grafo(base, config, i18n, llms)
        with Live(painel.tabela(), console=console, refresh_per_second=8) as ao_vivo:
            # "custom": avisos dos nós para o painel; "values": o estado completo,
            # já com os redutores aplicados (ex.: o histórico de correções)
            for modo, dado in grafo.stream(entrada, stream_mode=["custom", "values"]):
                if modo == "custom":
                    painel.atualizar(dado)
                    ao_vivo.update(painel.tabela())
                else:
                    estado = dado
        console.print()
    except ErroDeRegra as exc:
        _erro(f"Um agente violou uma regra: {exc}")
    except ValidationError as exc:
        _erro(f"Não foi possível montar o currículo: {exc}")
    except Exception as exc:  # noqa: BLE001 — erros de provedor variam: chave, cota, modelo
        _erro(descrever_erro(exc))

    if analise is None:
        salvar_analise(nome_vaga, texto_vaga, estado["analise"])

    validacao = estado["validacao"]
    fidelidade = estado.get("fidelidade")
    historico = estado.get("historico", [])
    alertas = validacao.alertas + (fidelidade.alertas if fidelidade else [])
    bloqueios = validacao.bloqueios + (fidelidade.bloqueios if fidelidade else [])
    if fidelidade is None:
        painel.nos["validar_fidelidade"].status = "pulado"
    if not historico:
        painel.nos["corrigir"].status = "pulado"

    # corte automático, só para currículo aprovado: remover nunca inventa nada
    cortes: list[str] = []
    if not bloqueios:
        notas = {a.origem: a.nota for a in estado["avaliacoes"]}
        cv, _, cortes = ajustar_paginas(
            estado["curriculo"], config.limites.paginas_max, notas
        )
        estado["curriculo"] = cv

    # registro da execução
    pasta = (
        Path("execucoes") / f"{datetime.now().astimezone():%Y-%m-%d_%H%M%S}_{nome_vaga}"
    )
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "analise_vaga.json").write_text(
        estado["analise"].model_dump_json(indent=2), encoding="utf-8"
    )
    (pasta / "curriculo.json").write_text(
        estado["curriculo"].model_dump_json(indent=2), encoding="utf-8"
    )
    incluidas = {x.origem for x in estado["experiencias"]}
    (pasta / "relatorio.md").write_text(
        gerar_relatorio(
            nome_vaga,
            estado["analise"],
            estado["avaliacoes"],
            incluidas,
            estado["omissoes"],
            validacao,
            fidelidade,
            painel,
            historico,
            cortes,
        ),
        encoding="utf-8",
    )

    for h in historico:
        typer.secho(
            f"CORREÇÃO {h['tentativa']}: {len(h['bloqueios'])} bloqueio(s); "
            f"refeitos: {', '.join(h['refeitos'])}",
            fg=typer.colors.CYAN,
        )
    for id_, motivo in estado["omissoes"].items():
        if "não gerou" in motivo or "não avaliou" in motivo:
            typer.secho(
                f"ALERTA   experiência {id_} omitida: {motivo}", fg=typer.colors.YELLOW
            )
    for corte in cortes:
        typer.secho(f"CORTE    {corte}", fg=typer.colors.YELLOW)
    for alerta in alertas:
        typer.secho(f"ALERTA   {alerta}", fg=typer.colors.YELLOW)
    for bloqueio in bloqueios:
        typer.secho(f"BLOQUEIO {bloqueio}", fg=typer.colors.RED)
    if bloqueios:
        motivo = (
            f"mesmo depois de {len(historico)} correção(ões) automática(s)"
            if historico
            else "e não pode ser corrigido automaticamente"
        )
        _erro(
            f"O currículo não passou na validação ({len(bloqueios)} bloqueio(s)), "
            f"{motivo}. Detalhes em {pasta / 'relatorio.md'}"
        )

    PASTA_CURRICULOS.mkdir(exist_ok=True)
    destino = PASTA_CURRICULOS / f"curriculo.{nome_vaga}.json"
    destino.write_text(estado["curriculo"].model_dump_json(indent=2), encoding="utf-8")
    typer.secho(f"Currículo gerado: {destino}", fg=typer.colors.GREEN)
    typer.echo(f"Relatório da execução: {pasta / 'relatorio.md'}")
    return destino


def _executar_pdf(arquivo: Path, paginas_max: int | None = None) -> Path:
    cv = _ler_curriculo(arquivo)
    destino = arquivo.with_suffix(".pdf")
    paginas = gerar_pdf(cv, destino)
    typer.secho(f"PDF gerado: {destino} ({paginas} página(s))", fg=typer.colors.GREEN)
    if paginas_max is not None and paginas > paginas_max:
        typer.secho(
            f"ALERTA   o PDF tem {paginas} páginas; o limite é {paginas_max}.",
            fg=typer.colors.YELLOW,
        )
    return destino


@app.command("json")
def gerar_json(vaga: VagaOpt, dados: DadosOpt = Path("dados")) -> None:
    """Roda os agentes e gera curriculos/curriculo.<nome_vaga>.json."""
    _executar_json(vaga, dados)


@app.command("pdf")
def gerar_pdf_cmd(
    arquivo: Annotated[Path, typer.Argument(help="Arquivo curriculo.<nome_vaga>.json")],
) -> None:
    """Gera o PDF a partir de um curriculo.<nome_vaga>.json."""
    _executar_pdf(arquivo)


@app.command("gerar")
def gerar(vaga: VagaOpt, dados: DadosOpt = Path("dados")) -> None:
    """Gera o JSON e depois o PDF."""
    arquivo_json = _executar_json(vaga, dados)
    _executar_pdf(arquivo_json, carregar_config().limites.paginas_max)


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
        f"  Experiências: {len(base.experiencias)} ({bullets} bullets, "
        f"{com_metrica} com métrica)"
    )
    typer.echo(f"  Projetos:     {len(base.projetos)}")
    typer.echo(f"  Formação:     {len(base.formacao)}")
    typer.echo(f"  Cursos:       {len(base.cursos)}")
    typer.echo(
        f"  Habilidades:  {len(hab.technical)} técnicas, "
        f"{len(hab.behavioral)} comportamentais"
    )
    typer.echo(f"  Idiomas:      {len(base.idiomas)}")
    typer.echo(f"  Headlines:    {', '.join(base.perfil.headlines)}")


@app.command("validar")
def validar(
    arquivo: Annotated[Path, typer.Argument(help="Arquivo curriculo.<nome_vaga>.json")],
    dados: DadosOpt = Path("dados"),
    fidelidade: Annotated[
        bool,
        typer.Option(
            "--fidelidade",
            help="Também confere o sentido com a LLM validadora (1 chamada)",
        ),
    ] = False,
) -> None:
    """Confere um currículo contra a base de dados: regras e, opcionalmente, fidelidade."""
    cv = _ler_curriculo(arquivo)
    base, i18n, config = _carregar_tudo(dados)
    resultado = validar_regras(cv, base, i18n, config)
    etapa = "regras"
    if resultado.aprovado and fidelidade:
        load_dotenv()
        try:
            llm = criar_llm(config.modelos.validador)
            extra = validar_fidelidade(cv, base, llm)
        except Exception as exc:  # noqa: BLE001 — erros de provedor variam
            _erro(descrever_erro(exc))
        resultado.alertas += extra.alertas
        resultado.bloqueios += extra.bloqueios
        etapa = "regras e na fidelidade"
    for alerta in resultado.alertas:
        typer.secho(f"ALERTA   {alerta}", fg=typer.colors.YELLOW)
    for bloqueio in resultado.bloqueios:
        typer.secho(f"BLOQUEIO {bloqueio}", fg=typer.colors.RED)
    if not resultado.aprovado:
        _erro(f"{len(resultado.bloqueios)} bloqueio(s): o currículo não passou.")
    typer.secho(
        f"Currículo aprovado nas {etapa} ({len(resultado.alertas)} alerta(s)).",
        fg=typer.colors.GREEN,
    )
