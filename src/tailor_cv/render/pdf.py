"""Script PDF: Curriculo -> PDF com ReportLab. Determinístico, sem LLM."""

import unicodedata
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


# A Helvetica padrão do PDF só tem os caracteres do Windows-1252. LLMs às vezes
# escrevem hífens e espaços "tipográficos" fora dessa tabela, que viram um
# quadrado preto no PDF. Estes são trocados pelo equivalente visível.
EQUIVALENTES = str.maketrans(
    {
        "\u2010": "-",  # hífen
        "\u2011": "-",  # hífen sem quebra ("e‑commerce")
        "\u2012": "–",  # traço numérico
        "\u2212": "-",  # sinal de menos
        "\u00ad": "",  # hífen condicional
        "\u2007": " ",  # espaços finos e especiais
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u200b": "",  # espaço de largura zero
        "\ufeff": "",
    }
)


def texto_seguro(texto: str) -> str:
    """Deixa só caracteres que a Helvetica consegue desenhar."""
    texto = texto.translate(EQUIVALENTES)
    saida = []
    for ch in texto:
        try:
            ch.encode("cp1252")
            saida.append(ch)
        except UnicodeEncodeError:
            # tenta a versão sem acento ou decoração; se não houver, descarta
            base = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
            saida.append(base)
    return "".join(saida)


def _e(texto: str) -> str:
    return escape(texto_seguro(texto))


def _secao(titulo: str, itens: list[Flowable]) -> list[Flowable]:
    """Título, linha e o primeiro item juntos: a quebra de página nunca deixa um
    título sozinho no fim da página, separado do conteúdo."""
    cabecalho: list[Flowable] = [
        Paragraph(_e(titulo.upper()), SECAO),
        HRFlowable(
            width="100%",
            thickness=0.8,
            color=colors.black,
            spaceBefore=3,
            spaceAfter=7,
        ),
    ]
    if not itens:
        return [KeepTogether(cabecalho)]
    # KeepTogether dentro de KeepTogether confunde o cálculo de altura do ReportLab
    # e força quebras de página desnecessárias: o primeiro item é "aberto" aqui
    primeiro = itens[0]._content if isinstance(itens[0], KeepTogether) else [itens[0]]
    return [KeepTogether([*cabecalho, *primeiro]), *itens[1:]]


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

    story += _secao("Resumo Profissional", [Paragraph(_e(cv.resumo), TEXTO)])

    experiencias = []
    for x in cv.experiencias:
        modo = f" ({x.modalidade})" if x.modalidade else ""
        titulo = (
            f"{x.empresa} – {x.cargo}{modo} | {data_pt(x.inicio)} – {data_pt(x.fim)}"
        )
        # uma experiência nunca é partida entre duas páginas
        experiencias.append(
            KeepTogether([Paragraph(_e(titulo), ITEM_TITULO), _bullets(x.bullets)])
        )
    story += _secao("Experiência Profissional", experiencias)

    if cv.projetos:
        projetos = []
        for p in cv.projetos:
            titulo = p.nome + (f" ({p.ano})" if p.ano else "")
            if p.reconhecimento:
                titulo += f" – {p.reconhecimento}"
            itens = [Paragraph(_e(titulo), ITEM_TITULO), _bullets(p.bullets)]
            if p.url:
                itens.append(Paragraph(_e(p.url), LINHA_ITEM))
            projetos.append(KeepTogether(itens))
        story += _secao("Projetos", projetos)

    if cv.formacao:
        linhas = [
            Paragraph(
                _e(f"{f.curso} – {f.instituicao} (Conclusão: {f.conclusao})"),
                LINHA_ITEM,
            )
            for f in cv.formacao
        ]
        story += _secao("Formação Acadêmica", linhas)

    if cv.cursos:
        linhas = []
        for k in cv.cursos:
            ano = f" ({k.ano})" if k.ano else ""
            linhas.append(Paragraph(_e(f"{k.nome} – {k.instituicao}{ano}"), LINHA_ITEM))
        story += _secao("Cursos", linhas)

    if cv.habilidades:
        texto = " • ".join(h.texto for h in cv.habilidades)
        story += _secao("Habilidades", [Paragraph(_e(texto), TEXTO)])

    if cv.idiomas:
        linha = " | ".join(f"{i.idioma}: {i.nivel}" for i in cv.idiomas)
        story += _secao("Idiomas", [Paragraph(_e(linha), TEXTO)])

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
