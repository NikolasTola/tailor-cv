"""Corte automático para o currículo caber no limite de páginas.

Só remove conteúdo, nunca reescreve: por isso o currículo cortado continua passando
nas validações. Ordem: primeiro os cursos (do fim da lista, os menos relevantes),
depois bullets das experiências com menor nota de relevância.
"""

import tempfile
from pathlib import Path

from tailor_cv.render.pdf import gerar_pdf
from tailor_cv.schemas import Curriculo


def ajustar_paginas(
    cv: Curriculo, paginas_max: int, notas: dict[str, int]
) -> tuple[Curriculo, int, list[str]]:
    """Devolve o currículo ajustado, o número de páginas e a lista do que foi cortado."""
    cv = cv.model_copy(deep=True)
    cortes: list[str] = []
    with tempfile.TemporaryDirectory() as pasta:
        rascunho = Path(pasta) / "rascunho.pdf"
        while True:
            paginas = gerar_pdf(cv, rascunho)
            if paginas <= paginas_max:
                return cv, paginas, cortes
            if cv.cursos:
                curso = cv.cursos.pop()
                cortes.append(f"curso removido: {curso.nome}")
                continue
            # a experiência de menor nota que ainda tem mais de um bullet;
            # entre notas iguais, a mais antiga
            candidatas = [x for x in cv.experiencias if len(x.bullets) > 1]
            if not candidatas:
                return cv, paginas, cortes  # não há mais o que cortar com segurança
            alvo = min(candidatas, key=lambda x: (notas.get(x.origem, 0), x.inicio))
            bullet = alvo.bullets.pop()
            cortes.append(f"bullet removido de {alvo.empresa}: {bullet.texto}")
