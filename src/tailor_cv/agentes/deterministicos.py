from typing import TypedDict

from tailor_cv.carregadores import I18n
from tailor_cv.schemas import Perfil
from tailor_cv.schemas.curriculo import Idioma, Modalidade
from tailor_cv.schemas.origem import IdiomaOrigem, ModoTrabalho


class ErroDeRegra(Exception):
    """Entrada que um agente de regra não sabe tratar (ex.: tradução faltando)."""


class TituloNome(TypedDict):
    nome: str
    headline: str


class DadosPessoais(TypedDict):
    cidade: str
    telefone: str
    email: str
    linkedin: str
    github: str | None


def titulo_e_nome(perfil: Perfil, headline: str) -> TituloNome:
    """Monta nome e headline. O headline precisa estar na lista aprovada do perfil.

    Quem escolhe o headline é o Analisador da vaga (LLM); esta regra garante que
    a escolha foi uma das opções permitidas, e nunca um cargo inventado.
    """
    if headline not in perfil.headlines:
        opcoes = ", ".join(perfil.headlines)
        raise ErroDeRegra(f"headline {headline!r} não está na lista aprovada: {opcoes}")
    return {"nome": perfil.name, "headline": headline}


def dados_pessoais(perfil: Perfil) -> DadosPessoais:
    return {
        "cidade": perfil.city,
        "telefone": perfil.phone,
        "email": perfil.email,
        "linkedin": perfil.linkedin,
        "github": perfil.github,
    }


def idiomas(lista: list[IdiomaOrigem], i18n: I18n) -> list[Idioma]:
    """Traduz nomes e níveis por dicionário, mantendo a ordem do idiomas.md."""
    sem_traducao = sorted({i.language for i in lista} - set(i18n.idiomas))
    if sem_traducao:
        raise ErroDeRegra(
            f"idiomas sem tradução no i18n_pt.yaml: {', '.join(sem_traducao)}. "
            "Adicione-os na seção 'idiomas'."
        )
    return [
        Idioma(idioma=i18n.idiomas[i.language], nivel=i18n.niveis[i.level])
        for i in lista
    ]


def modalidade(work_mode: ModoTrabalho | None, i18n: I18n) -> Modalidade | None:
    """'hybrid' -> 'Híbrido'. Usado ao montar as experiências no currículo."""
    return i18n.modalidades[work_mode] if work_mode else None
