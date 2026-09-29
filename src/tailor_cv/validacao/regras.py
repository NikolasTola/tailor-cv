import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from tailor_cv.agentes import idiomas as traduzir_idiomas
from tailor_cv.agentes import modalidade
from tailor_cv.carregadores import I18n
from tailor_cv.config import Config
from tailor_cv.schemas import BaseDados, Curriculo

Agente = Literal[
    "titulo_e_nome",
    "dados_pessoais",
    "idiomas",
    "experiencia",
    "formacao",
    "cursos",
    "resumo",
    "habilidades",
]

NUMERO = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*")
MILHAR_PT = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")
MILHAR_EN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")


@dataclass(frozen=True)
class Problema:
    agente: Agente
    verificacao: str
    local: str
    mensagem: str

    def __str__(self) -> str:
        return f"[{self.agente}] {self.local}: {self.mensagem}"


@dataclass
class ResultadoValidacao:
    bloqueios: list[Problema] = field(default_factory=list)
    alertas: list[Problema] = field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return not self.bloqueios


# ---------- utilitários ----------


def _normalizar(bruto: str, milhar: re.Pattern[str], sep_milhar: str) -> str | None:
    texto = bruto
    if milhar.fullmatch(texto):
        texto = texto.replace(sep_milhar, "")
    texto = texto.replace(",", ".")
    try:
        return str(Decimal(texto).normalize())
    except InvalidOperation:
        return None


def numeros_pt(texto: str) -> set[str]:
    """'2.000 colaboradores e 2,5x' -> {'2E+3', '2.5'}"""
    return {
        n
        for m in NUMERO.findall(texto)
        if (n := _normalizar(m, MILHAR_PT, ".")) is not None
    }


def numeros_en(texto: str) -> set[str]:
    """'2,000 employees and 2.5x' -> {'2E+3', '2.5'}"""
    return {
        n
        for m in NUMERO.findall(texto)
        if (n := _normalizar(m, MILHAR_EN, ",")) is not None
    }


def _contem_termo(texto: str, termo: str) -> bool:
    return (
        re.search(rf"(?<!\w){re.escape(termo)}(?!\w)", texto, re.IGNORECASE) is not None
    )


def _vocabulario_tecnico(base: BaseDados) -> set[str]:
    termos = {t for x in base.experiencias for a in x.achievements for t in a.tech}
    termos |= {t for c in base.cursos for t in c.tech}
    termos |= set(base.habilidades.technical)
    return termos


def _termos_sem_lastro(
    texto: str, vocabulario: set[str], permitidos: list[str], texto_origem: str
) -> list[str]:
    """Tecnologias citadas no texto que não aparecem nas tags nem no texto de origem."""
    permitidos_min = [p.lower() for p in permitidos]
    origem_min = texto_origem.lower()
    return sorted(
        termo
        for termo in vocabulario
        if _contem_termo(texto, termo)
        and not any(termo.lower() in p for p in permitidos_min)
        and termo.lower() not in origem_min
    )


class _Coletor:
    def __init__(self) -> None:
        self.resultado = ResultadoValidacao()

    def bloqueio(self, agente: Agente, verificacao: str, local: str, msg: str) -> None:
        self.resultado.bloqueios.append(Problema(agente, verificacao, local, msg))

    def alerta(self, agente: Agente, verificacao: str, local: str, msg: str) -> None:
        self.resultado.alertas.append(Problema(agente, verificacao, local, msg))


def _checar_texto(
    col: _Coletor,
    agente: Agente,
    local: str,
    texto: str,
    *,
    limite_palavras: int,
    proibidas: list[str],
    numeros_origem: set[str],
    vocabulario: set[str],
    tags_permitidas: list[str],
    texto_origem: str,
) -> None:
    """Verificações comuns a bullets e ao resumo."""
    # guarda o número como está escrito, para a mensagem ficar legível ("3.000")
    inventados = sorted(
        {
            bruto
            for bruto in NUMERO.findall(texto)
            if _normalizar(bruto, MILHAR_PT, ".") not in numeros_origem
        }
    )
    if inventados:
        col.bloqueio(
            agente,
            "numero_sem_origem",
            local,
            f"número(s) que não existem na origem: {', '.join(inventados)}. "
            "Adicione-os em 'metric:' do bullet de origem ou remova-os do texto.",
        )
    sem_lastro = _termos_sem_lastro(texto, vocabulario, tags_permitidas, texto_origem)
    if sem_lastro:
        col.bloqueio(
            agente,
            "tecnologia_sem_lastro",
            local,
            f"tecnologia(s) fora das tags de origem: {', '.join(sem_lastro)}",
        )
    achadas = [p for p in proibidas if _contem_termo(texto, p)]
    if achadas:
        col.bloqueio(
            agente,
            "palavra_proibida",
            local,
            f"palavra(s) proibida(s): {', '.join(achadas)}",
        )
    palavras = len(texto.split())
    if palavras > limite_palavras:
        col.alerta(
            agente,
            "texto_longo",
            local,
            f"{palavras} palavras (limite: {limite_palavras})",
        )


# ---------- validação ----------


def validar_regras(
    cv: Curriculo, base: BaseDados, i18n: I18n, config: Config
) -> ResultadoValidacao:
    col = _Coletor()
    vocabulario = _vocabulario_tecnico(base)
    proibidas = config.palavras_proibidas
    limites = config.limites

    # Cabeçalho
    p, c = base.perfil, cv.cabecalho
    if c.headline not in p.headlines:
        col.bloqueio(
            "titulo_e_nome",
            "headline_fora_da_lista",
            "cabecalho.headline",
            f"{c.headline!r} não está na lista aprovada do perfil.yaml",
        )
    if c.nome != p.name:
        col.bloqueio(
            "titulo_e_nome", "divergente", "cabecalho.nome", "difere do perfil.yaml"
        )
    esperado = {
        "cidade": p.city,
        "telefone": p.phone,
        "email": p.email,
        "linkedin": p.linkedin,
        "github": p.github,
    }
    for campo, valor in esperado.items():
        if getattr(c, campo) != valor:
            col.bloqueio(
                "dados_pessoais",
                "divergente",
                f"cabecalho.{campo}",
                "difere do perfil.yaml",
            )

    # Experiências
    por_id = {x.id: x for x in base.experiencias}
    vistas: set[str] = set()
    tags_selecionadas: list[str] = []
    numeros_selecionados: set[str] = set()
    textos_selecionados: list[str] = []

    for i, x in enumerate(cv.experiencias):
        local = f"experiencias[{i}] ({x.origem})"
        origem = por_id.get(x.origem)
        if origem is None:
            col.bloqueio(
                "experiencia",
                "origem_inexistente",
                local,
                "experiência não existe na base",
            )
            continue
        if x.origem in vistas:
            col.bloqueio(
                "experiencia", "duplicada", local, "experiência repetida no currículo"
            )
        vistas.add(x.origem)

        if x.empresa != origem.company:
            col.bloqueio(
                "experiencia",
                "divergente",
                local,
                f"empresa difere da origem ({origem.company})",
            )
        if (x.inicio, x.fim) != (origem.start, origem.end):
            col.bloqueio(
                "experiencia",
                "divergente",
                local,
                f"datas diferem da origem ({origem.start} a {origem.end or 'atual'})",
            )
        if x.modalidade != modalidade(origem.work_mode, i18n):
            col.bloqueio(
                "experiencia", "divergente", local, "modalidade difere da origem"
            )

        conquistas = {a.id: a for a in origem.achievements}
        for j, b in enumerate(x.bullets):
            local_b = f"{local}.bullets[{j}]"
            faltando = [o for o in b.origem if o not in conquistas]
            if faltando:
                col.bloqueio(
                    "experiencia",
                    "bullet_sem_origem",
                    local_b,
                    f"ID(s) de origem inexistente(s) em {x.origem}: {', '.join(faltando)}",
                )
                continue
            fontes = [conquistas[o] for o in b.origem]
            texto_origem = " ".join(f"{a.text} {a.metric or ''}" for a in fontes)
            tags = [t for a in fontes for t in a.tech]
            numeros = numeros_en(texto_origem)
            _checar_texto(
                col,
                "experiencia",
                local_b,
                b.texto,
                limite_palavras=limites.bullet_palavras_max,
                proibidas=proibidas,
                numeros_origem=numeros,
                vocabulario=vocabulario,
                tags_permitidas=tags,
                texto_origem=texto_origem,
            )
            tags_selecionadas += tags
            numeros_selecionados |= numeros
            textos_selecionados.append(texto_origem)

    obrigatorias = [
        x.id for x in base.experiencias if x.always_include and x.id not in vistas
    ]
    if obrigatorias:
        col.bloqueio(
            "experiencia",
            "obrigatoria_omitida",
            "experiencias",
            f"marcadas com always_include e ausentes: {', '.join(obrigatorias)}",
        )

    # Formação
    formacoes = {f.id: f for f in base.formacao}
    for i, f in enumerate(cv.formacao):
        local = f"formacao[{i}] ({f.origem})"
        origem = formacoes.get(f.origem)
        if origem is None:
            col.bloqueio(
                "formacao", "origem_inexistente", local, "formação não existe na base"
            )
            continue
        if f.instituicao != origem.institution:
            col.bloqueio(
                "formacao", "divergente", local, "instituição difere da origem"
            )
        if str(origem.completion) not in f.conclusao:
            col.bloqueio(
                "formacao",
                "divergente",
                local,
                f"ano de conclusão difere ({origem.completion})",
            )

    # Cursos
    cursos = {k.id: k for k in base.cursos}
    for i, k in enumerate(cv.cursos):
        local = f"cursos[{i}] ({k.origem})"
        origem = cursos.get(k.origem)
        if origem is None:
            col.bloqueio(
                "cursos", "origem_inexistente", local, "curso não existe na base"
            )
            continue
        tags_selecionadas += origem.tech
        if k.instituicao != origem.provider:
            col.bloqueio("cursos", "divergente", local, "instituição difere da origem")
        ano_origem = str(origem.year) if origem.year else None
        if k.ano != ano_origem:
            col.bloqueio(
                "cursos", "divergente", local, f"ano difere da origem ({ano_origem})"
            )

    # Habilidades
    tecnicas, comportamentais = base.habilidades.technical, base.habilidades.behavioral
    for i, h in enumerate(cv.habilidades):
        local = f"habilidades[{i}] ({h.origem})"
        if h.origem not in tecnicas and h.origem not in comportamentais:
            col.bloqueio(
                "habilidades",
                "fora_da_base",
                local,
                "habilidade não está no habilidades.md",
            )
        elif h.origem in tecnicas and h.texto != h.origem:
            col.alerta(
                "habilidades",
                "termo_traduzido",
                local,
                f"habilidade técnica deveria ficar como {h.origem!r}",
            )
    tags_selecionadas += [h.origem for h in cv.habilidades]

    # Resumo: só pode citar o que foi selecionado
    _checar_texto(
        col,
        "resumo",
        "resumo",
        cv.resumo,
        limite_palavras=limites.resumo_palavras_max,
        proibidas=proibidas,
        numeros_origem=numeros_selecionados,
        vocabulario=vocabulario,
        tags_permitidas=tags_selecionadas,
        texto_origem=" ".join(textos_selecionados),
    )

    # Idiomas: precisam ser exatamente a tradução por regra
    if cv.idiomas != traduzir_idiomas(base.idiomas, i18n):
        col.bloqueio(
            "idiomas", "divergente", "idiomas", "diferem da tradução do idiomas.md"
        )

    return col.resultado
