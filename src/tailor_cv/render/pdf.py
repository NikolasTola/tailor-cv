"""Script PDF: Curriculo -> PDF com ReportLab. Determinístico, sem LLM."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
)

from tailor_cv.schemas import Curriculo
from tailor_cv.schemas.curriculo import Bullet

MESES = [
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
]


def data_pt(ano_mes: str | None) -> str:
    """'2021-01' -> 'Jan/2021'; None -> 'Atual'."""
    if ano_mes is None:
        return "Atual"
    ano, mes = ano_mes.split("-")
    return f"{MESES[int(mes) - 1]}/{ano}"


def _estilo(**k) -> ParagraphStyle:
    base = {"fontName": "Helvetica", "fontSize": 10.5, "leading": 15}
    return ParagraphStyle("s", **{**base, **k})


NOME = _estilo(fontName="Helvetica-Bold", fontSize=17, leading=22, alignment=TA_CENTER)
HEADLINE = _estilo(fontSize=12, leading=16, alignment=TA_CENTER, spaceAfter=10)
CONTATO = _estilo(leading=14.5)
SECAO = _estilo(fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceBefore=16)
TEXTO = _estilo()
ITEM_TITULO = _estilo(fontName="Helvetica-Bold", spaceBefore=9, spaceAfter=4)
LINHA_ITEM = _estilo(spaceAfter=3)


def _e(texto: str) -> str:
    return escape(texto)


def _secao(titulo: str) -> Flowable:
    # título + linha juntos, para a quebra de página nunca separar os dois
    return KeepTogether(
        [
            Paragraph(_e(titulo.upper()), SECAO),
            HRFlowable(
                width="100%",
                thickness=0.8,
                color=colors.black,
                spaceBefore=3,
                spaceAfter=7,
            ),
        ]
    )


def _bullets(bullets: list[Bullet]) -> Flowable:
    return ListFlowable(
        [ListItem(Paragraph(_e(b.texto), LINHA_ITEM), leftIndent=12) for b in bullets],
        bulletType="bullet",
        start="•",
        bulletFontName="Helvetica",
        leftIndent=12,
    )


def _montar(cv: Curriculo) -> list[Flowable]:
    c = cv.cabecalho
    story: list[Flowable] = [
        Paragraph(_e(c.nome.upper()), NOME),
        Paragraph(_e(c.headline), HEADLINE),
    ]
    for linha in (c.cidade, c.telefone, c.email, f"LinkedIn: {c.linkedin}"):
        story.append(Paragraph(_e(linha), CONTATO))
    if c.github:
        story.append(Paragraph(_e(f"GitHub: {c.github}"), CONTATO))

    story += [_secao("Resumo Profissional"), Paragraph(_e(cv.resumo), TEXTO)]

    story.append(_secao("Experiência Profissional"))
    for x in cv.experiencias:
        modo = f" ({x.modalidade})" if x.modalidade else ""
        titulo = (
            f"{x.empresa} – {x.cargo}{modo} | {data_pt(x.inicio)} – {data_pt(x.fim)}"
        )
        # uma experiência nunca é partida entre duas páginas
        story.append(
            KeepTogether([Paragraph(_e(titulo), ITEM_TITULO), _bullets(x.bullets)])
        )

    if cv.projetos:
        story.append(_secao("Projetos"))
        for p in cv.projetos:
            titulo = p.nome + (f" ({p.ano})" if p.ano else "")
            if p.reconhecimento:
                titulo += f" – {p.reconhecimento}"
            itens = [Paragraph(_e(titulo), ITEM_TITULO), _bullets(p.bullets)]
            if p.url:
                itens.append(Paragraph(_e(p.url), LINHA_ITEM))
            story.append(KeepTogether(itens))

    if cv.formacao:
        story.append(_secao("Formação Acadêmica"))
        for f in cv.formacao:
            story.append(
                Paragraph(
                    _e(f"{f.curso} – {f.instituicao} (Conclusão: {f.conclusao})"),
                    LINHA_ITEM,
                )
            )

    if cv.cursos:
        story.append(_secao("Cursos"))
        for k in cv.cursos:
            ano = f" ({k.ano})" if k.ano else ""
            story.append(Paragraph(_e(f"{k.nome} – {k.instituicao}{ano}"), LINHA_ITEM))

    if cv.habilidades:
        story += [
            _secao("Habilidades"),
            Paragraph(_e(" • ".join(h.texto for h in cv.habilidades)), TEXTO),
        ]

    if cv.idiomas:
        linha = " | ".join(f"{i.idioma}: {i.nivel}" for i in cv.idiomas)
        story += [_secao("Idiomas"), Paragraph(_e(linha), TEXTO)]

    return story


def gerar_pdf(cv: Curriculo, destino: Path) -> int:
    """Gera o PDF em `destino` e devolve o número de páginas."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(destino),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=f"Currículo – {cv.cabecalho.nome}",
        author=cv.cabecalho.nome,
    )
    doc.build(_montar(cv))
    return doc.page
