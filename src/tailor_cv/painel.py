"""Painel ao vivo no terminal, alimentado pelos avisos dos nós do grafo."""

from dataclasses import dataclass

from rich.table import Table
from rich.text import Text

from tailor_cv.grafo import NOS

ROTULOS = {
    "analisador": "Analisador da vaga",
    "dados_pessoais": "Dados pessoais",
    "idiomas": "Idiomas",
    "formacao": "Formação",
    "titulo_e_nome": "Título e nome",
    "experiencia": "Experiência",
    "cursos": "Cursos",
    "habilidades": "Habilidades",
    "resumo": "Resumo",
    "montar": "Montar currículo",
    "validar_regras": "Validar regras",
}
LLM = {"analisador", "formacao", "experiencia", "cursos", "habilidades", "resumo"}
ESTILO = {
    "aguardando": ("·  aguardando", "dim"),
    "rodando": ("…  rodando", "yellow"),
    "ok": ("✓  ok", "green"),
    "cache": ("✓  cache", "cyan"),
    "erro": ("✗  erro", "red"),
}


@dataclass
class StatusNo:
    status: str = "aguardando"
    segundos: float | None = None


class Painel:
    def __init__(self) -> None:
        self.nos = {nome: StatusNo() for nome, _ in NOS}

    def atualizar(self, evento: dict) -> None:
        no = self.nos.get(evento.get("no", ""))
        if no is not None:
            no.status = evento["status"]
            no.segundos = evento.get("segundos")

    def tabela(self) -> Table:
        tabela = Table(title="TailorCV", title_justify="left", box=None, padding=(0, 2))
        tabela.add_column("Onda", justify="center", style="dim")
        tabela.add_column("Agente")
        tabela.add_column("Tipo", style="dim")
        tabela.add_column("Status")
        tabela.add_column("Tempo", justify="right", style="dim")
        for nome, onda in NOS:
            no = self.nos[nome]
            texto, estilo = ESTILO[no.status]
            tempo = f"{no.segundos:.1f}s" if no.segundos is not None else ""
            tipo = "LLM" if nome in LLM else "regra"
            tabela.add_row(
                str(onda), ROTULOS[nome], tipo, Text(texto, style=estilo), tempo
            )
        return tabela
