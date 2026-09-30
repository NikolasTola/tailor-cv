"""Relatório de cada execução, salvo em execucoes/<data>_<vaga>/relatorio.md."""

from tailor_cv.painel import ROTULOS, Painel
from tailor_cv.schemas.agentes import AnaliseVaga, AvaliacaoExperiencia
from tailor_cv.validacao import ResultadoValidacao


def gerar_relatorio(
    nome_vaga: str,
    analise: AnaliseVaga,
    avaliacoes: list[AvaliacaoExperiencia],
    incluidas: set[str],
    omissoes: dict[str, str],
    validacao: ResultadoValidacao | None,
    fidelidade: ResultadoValidacao | None,
    painel: Painel,
    historico: list[dict] | None = None,
    cortes: list[str] | None = None,
) -> str:
    linhas = [
        f"# Relatório: {nome_vaga}",
        "",
        f"**Vaga:** {analise.cargo} ({analise.senioridade})  ",
        f"**Headline escolhido:** {analise.headline}",
        "",
        "## Experiências",
        "",
        "| Nota | Situação | Experiência | Justificativa |",
        "| --- | --- | --- | --- |",
    ]
    notas = {a.origem: a for a in avaliacoes}
    ids = sorted(
        set(notas) | set(omissoes) | incluidas,
        key=lambda i: -(notas[i].nota if i in notas else -1),
    )
    for id_ in ids:
        a = notas.get(id_)
        situacao = (
            "incluída" if id_ in incluidas else f"omitida: {omissoes.get(id_, '?')}"
        )
        nota = a.nota if a else "-"
        justificativa = a.justificativa if a else "-"
        linhas.append(f"| {nota} | {situacao} | {id_} | {justificativa} |")

    for titulo, resultado in (
        ("Validação de regras", validacao),
        ("Validação de fidelidade", fidelidade),
    ):
        linhas += ["", f"## {titulo}", ""]
        if resultado is None:
            linhas.append("Não executada.")
        elif not resultado.bloqueios and not resultado.alertas:
            linhas.append("Nenhum problema encontrado.")
        else:
            linhas += [f"- **Bloqueio:** {p}" for p in resultado.bloqueios]
            linhas += [f"- Alerta: {p}" for p in resultado.alertas]

    if historico:
        linhas += ["", "## Correções automáticas", ""]
        for h in historico:
            linhas.append(
                f"**Tentativa {h['tentativa']}:** refeitos {', '.join(h['refeitos'])}"
            )
            linhas += [f"- {b}" for b in h["bloqueios"]]
            linhas.append("")

    if cortes:
        linhas += ["", "## Cortes para caber no limite de páginas", ""]
        linhas += [f"- {c}" for c in cortes]

    linhas += [
        "",
        "## Tempo por agente",
        "",
        "| Agente | Status | Tempo |",
        "| --- | --- | --- |",
    ]
    for nome, no in painel.nos.items():
        tempo = f"{no.segundos:.1f}s" if no.segundos is not None else "-"
        linhas.append(f"| {ROTULOS[nome]} | {no.status} | {tempo} |")
    return "\n".join(linhas) + "\n"
