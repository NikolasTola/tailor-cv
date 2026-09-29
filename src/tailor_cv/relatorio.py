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
    painel: Painel,
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

    if validacao is not None:
        linhas += ["", "## Validação de regras", ""]
        if not validacao.bloqueios and not validacao.alertas:
            linhas.append("Nenhum problema encontrado.")
        linhas += [f"- **Bloqueio:** {p}" for p in validacao.bloqueios]
        linhas += [f"- Alerta: {p}" for p in validacao.alertas]

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
