"""Leitura da base de dados pessoal (Markdown e YAML) para os schemas de origem.

Tudo aqui é determinístico: nenhum arquivo passa por LLM nesta etapa.
Erros sempre apontam o arquivo e, quando possível, a linha.
"""

import re
from pathlib import Path
from typing import Any

import frontmatter
import yaml
from pydantic import BaseModel, ValidationError

from tailor_cv.schemas import (
    BaseDados,
    CursoOrigem,
    ExperienciaOrigem,
    FormacaoOrigem,
    Habilidades,
    IdiomaOrigem,
    Perfil,
    ProjetoOrigem,
)

BULLET_COM_ID = re.compile(r"^- \[([^\]]+)\]\s+(.+)$")
SUB_ITEM = re.compile(r"^\s{2,}- (tech|metric):\s*(.*)$")
ITEM = re.compile(r"^- (.+)$")
IDIOMA = re.compile(r"^- ([^:]+):\s*(.+)$")


class ErroDeOrigem(Exception):
    """Problema num arquivo da base de dados, com o local exato."""


def _ler_frontmatter(arquivo: Path) -> tuple[frontmatter.Post, str]:
    """Lê o arquivo e o frontmatter; um YAML inválido vira erro com o arquivo."""
    texto = arquivo.read_text(encoding="utf-8")
    try:
        return frontmatter.loads(texto), texto
    except yaml.YAMLError as exc:
        dica = ""
        if "mapping values" in str(exc):
            dica = ' Dica: um valor com ":" precisa estar entre aspas.'
        raise ErroDeOrigem(
            f"{arquivo}: YAML inválido no frontmatter: {exc}.{dica}"
        ) from None


def _validar[M: BaseModel](modelo: type[M], dados: dict[str, Any], arquivo: Path) -> M:
    try:
        return modelo.model_validate(dados)
    except ValidationError as exc:
        erros = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'arquivo'}: {e['msg']}"
            for e in exc.errors()
        )
        raise ErroDeOrigem(f"{arquivo}: {erros}") from None


def _secoes(corpo: str, deslocamento: int = 0) -> dict[str, list[tuple[int, str]]]:
    """Separa o corpo Markdown por títulos '## ', guardando o número de cada linha.

    `deslocamento` = linhas antes do corpo (o frontmatter), para o número bater com o
    que o editor mostra.
    """
    secoes: dict[str, list[tuple[int, str]]] = {}
    atual = None
    for n, linha in enumerate(corpo.splitlines(), start=1 + deslocamento):
        if linha.startswith("## "):
            atual = linha[3:].strip().lower()
            secoes[atual] = []
        elif atual is not None and linha.strip():
            secoes[atual].append((n, linha.rstrip()))
    return secoes


def _arquivos_md(pasta: Path) -> list[Path]:
    # arquivos que começam com "_" são ignorados: servem de modelo/rascunho
    return sorted(p for p in pasta.glob("*.md") if not p.name.startswith("_"))


def carregar_perfil(arquivo: Path) -> Perfil:
    try:
        dados = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ErroDeOrigem(f"{arquivo}: YAML inválido: {exc}") from None
    return _validar(Perfil, dados, arquivo)


def _ler_com_conquistas(arquivo: Path) -> tuple[dict[str, Any], str | None, list]:
    """Frontmatter, contexto e conquistas de um arquivo de experiência ou projeto."""
    post, texto = _ler_frontmatter(arquivo)
    meta = dict(post.metadata)

    deslocamento = texto[: texto.find(post.content)].count("\n") if post.content else 0
    secoes = _secoes(post.content, deslocamento)
    contexto = " ".join(linha.strip() for _, linha in secoes.get("context", [])) or None

    conquistas: list[dict[str, Any]] = []
    for n, linha in secoes.get("achievements", []):
        local = f"{arquivo} (linha {n})"
        if m := BULLET_COM_ID.match(linha):
            conquistas.append({"id": m[1].strip(), "text": m[2].strip()})
        elif m := SUB_ITEM.match(linha):
            if not conquistas:
                raise ErroDeOrigem(
                    f"{local}: '{m[1]}:' aparece antes de qualquer bullet"
                )
            chave, valor = m[1], m[2].strip()
            if chave == "tech":
                conquistas[-1]["tech"] = [
                    t.strip() for t in valor.split(",") if t.strip()
                ]
            elif valor:
                conquistas[-1]["metric"] = valor
        elif linha.startswith("- "):
            raise ErroDeOrigem(
                f"{local}: bullet sem ID. Use o formato '- [meu-id] Texto'"
            )
        else:
            raise ErroDeOrigem(f"{local}: linha não reconhecida: {linha.strip()!r}")
    return meta, contexto, conquistas


def carregar_experiencia(arquivo: Path) -> ExperienciaOrigem:
    meta, contexto, conquistas = _ler_com_conquistas(arquivo)
    if str(meta.get("end", "")).strip().lower() == "present":
        meta["end"] = None
    return _validar(
        ExperienciaOrigem,
        {**meta, "context": contexto, "achievements": conquistas},
        arquivo,
    )


def carregar_projeto(arquivo: Path) -> ProjetoOrigem:
    meta, contexto, conquistas = _ler_com_conquistas(arquivo)
    return _validar(
        ProjetoOrigem,
        {**meta, "context": contexto, "achievements": conquistas},
        arquivo,
    )


def carregar_formacao(arquivo: Path) -> FormacaoOrigem:
    post, _ = _ler_frontmatter(arquivo)
    notas = post.content.strip() or None
    return _validar(FormacaoOrigem, {**post.metadata, "notes": notas}, arquivo)


def carregar_curso(arquivo: Path) -> CursoOrigem:
    post, _ = _ler_frontmatter(arquivo)
    return _validar(CursoOrigem, dict(post.metadata), arquivo)


def carregar_habilidades(arquivo: Path) -> Habilidades:
    secoes = _secoes(arquivo.read_text(encoding="utf-8"))
    desconhecidas = set(secoes) - {"technical", "behavioral"}
    if desconhecidas:
        raise ErroDeOrigem(
            f"{arquivo}: seções desconhecidas: {', '.join(sorted(desconhecidas))}"
        )
    dados: dict[str, list[str]] = {}
    for secao, linhas in secoes.items():
        itens = []
        for n, linha in linhas:
            if not (m := ITEM.match(linha)):
                raise ErroDeOrigem(
                    f"{arquivo} (linha {n}): esperado '- Habilidade', veio {linha.strip()!r}"
                )
            itens.append(m[1].strip())
        dados[secao] = itens
    return _validar(Habilidades, dados, arquivo)


def carregar_idiomas(arquivo: Path) -> list[IdiomaOrigem]:
    idiomas = []
    for n, linha in enumerate(
        arquivo.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not linha.strip() or linha.startswith("#"):
            continue
        if not (m := IDIOMA.match(linha)):
            raise ErroDeOrigem(
                f"{arquivo} (linha {n}): esperado '- Language: level', veio {linha.strip()!r}"
            )
        dados = {"language": m[1].strip(), "level": m[2].strip().lower()}
        idiomas.append(_validar(IdiomaOrigem, dados, Path(f"{arquivo} (linha {n})")))
    return idiomas


def carregar_base(pasta: Path) -> BaseDados:
    """Lê a base inteira. Qualquer problema vira ErroDeOrigem com o arquivo culpado."""
    obrigatorios = ["perfil.yaml", "habilidades.md", "experiencias"]
    faltando = [nome for nome in obrigatorios if not (pasta / nome).exists()]
    if faltando:
        raise ErroDeOrigem(f"{pasta}: faltam {', '.join(faltando)}")

    def opcional(nome: str) -> Path | None:
        caminho = pasta / nome
        return caminho if caminho.exists() else None

    pasta_formacao, pasta_cursos, arq_idiomas = (
        opcional("formacao"),
        opcional("cursos"),
        opcional("idiomas.md"),
    )
    pasta_projetos = opcional("projetos")
    dados = {
        "perfil": carregar_perfil(pasta / "perfil.yaml"),
        "experiencias": [
            carregar_experiencia(a) for a in _arquivos_md(pasta / "experiencias")
        ],
        "projetos": [carregar_projeto(a) for a in _arquivos_md(pasta_projetos)]
        if pasta_projetos
        else [],
        "formacao": [carregar_formacao(a) for a in _arquivos_md(pasta_formacao)]
        if pasta_formacao
        else [],
        "cursos": [carregar_curso(a) for a in _arquivos_md(pasta_cursos)]
        if pasta_cursos
        else [],
        "habilidades": carregar_habilidades(pasta / "habilidades.md"),
        "idiomas": carregar_idiomas(arq_idiomas) if arq_idiomas else [],
    }
    try:
        return BaseDados.model_validate(dados)
    except ValidationError as exc:
        raise ErroDeOrigem(
            "; ".join(f"{pasta}: {e['msg']}" for e in exc.errors())
        ) from None
