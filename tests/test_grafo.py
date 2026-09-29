import threading
import time
from pathlib import Path

import pytest
from llm_falsa import LLMFalsa
from test_agentes_llm import ANALISE, _saida
from test_agentes_secoes import CURSOS, FORMACAO, HABILIDADES, RESUMO

from tailor_cv.carregadores import carregar_base, carregar_i18n
from tailor_cv.config import carregar_config
from tailor_cv.grafo import NOS, construir_grafo
from tailor_cv.painel import Painel
from tailor_cv.schemas.agentes import SaidaFidelidade

RAIZ = Path(__file__).parent.parent
BASE = carregar_base(RAIZ / "exemplos" / "dados")
I18N = carregar_i18n(RAIZ / "i18n_pt.yaml")
CONFIG = carregar_config(RAIZ / "config.yaml")
AGENTES = (
    "analisador",
    "experiencia",
    "formacao",
    "cursos",
    "habilidades",
    "resumo",
    "validador",
)
FIEL = SaidaFidelidade(problemas=[])


def _llm() -> LLMFalsa:
    # uma única LLM falsa responde a todos: ela escolhe a resposta pelo schema
    return LLMFalsa(ANALISE, _saida(), FORMACAO, CURSOS, HABILIDADES, RESUMO, FIEL)


def _rodar(entrada: dict, llm: LLMFalsa | None = None) -> tuple[dict, list[dict]]:
    llm = llm or _llm()
    grafo = construir_grafo(BASE, CONFIG, I18N, dict.fromkeys(AGENTES, llm))
    estado, eventos = dict(entrada), []
    for modo, dado in grafo.stream(entrada, stream_mode=["custom", "updates"]):
        if modo == "custom":
            eventos.append(dado)
        else:
            for atualizacao in dado.values():
                estado.update(atualizacao or {})
    return estado, eventos


def test_grafo_completo_gera_curriculo_aprovado():
    estado, _ = _rodar({"texto_vaga": "vaga"})
    cv = estado["curriculo"]
    assert cv.cabecalho.headline == "Engenheira de IA"
    assert [x.origem for x in cv.experiencias] == ["empresa-alfa", "empresa-beta"]
    assert cv.formacao[0].curso == "Bacharelado em Estatística"
    assert [h.texto for h in cv.habilidades][:1] == ["Python"]
    assert estado["validacao"].aprovado, estado["validacao"].bloqueios


def test_todos_os_nos_avisam_inicio_e_fim():
    _, eventos = _rodar({"texto_vaga": "vaga"})
    finais = {e["no"]: e["status"] for e in eventos if e["status"] != "rodando"}
    assert finais == {nome: "ok" for nome, _ in NOS}


def test_analise_em_cache_pula_a_llm_do_analisador():
    llm = _llm()
    _, eventos = _rodar({"texto_vaga": "vaga", "analise": ANALISE}, llm)
    assert {"no": "analisador", "status": "cache"}.items() <= next(
        e for e in eventos if e["no"] == "analisador" and e["status"] != "rodando"
    ).items()
    schemas = [c[0].content[:40] for c in llm.chamadas]
    assert not any("Analisador de vagas" in s for s in schemas)


def test_ondas_respeitam_as_dependencias():
    _, eventos = _rodar({"texto_vaga": "vaga"})
    ordem = [e["no"] for e in eventos if e["status"] == "ok"]
    assert ordem.index("analisador") < ordem.index("experiencia")
    assert ordem.index("experiencia") < ordem.index("habilidades")
    assert ordem.index("cursos") < ordem.index("resumo")
    assert ordem[-3:] == ["montar", "validar_regras", "validar_fidelidade"]


class LLMLenta(LLMFalsa):
    """Cada chamada demora; registra quantas rodam ao mesmo tempo."""

    def __init__(self, *respostas):
        super().__init__(*respostas)
        self.ativas = self.pico = 0
        self.trava = threading.Lock()

    def with_structured_output(self, schema, **kw):
        interno = super().with_structured_output(schema, **kw)
        llm = self

        class Lento:
            def invoke(self, mensagens):
                with llm.trava:
                    llm.ativas += 1
                    llm.pico = max(llm.pico, llm.ativas)
                time.sleep(0.2)
                with llm.trava:
                    llm.ativas -= 1
                return interno.invoke(mensagens)

        return Lento()


def test_agentes_da_mesma_onda_rodam_em_paralelo():
    llm = LLMLenta(ANALISE, _saida(), FORMACAO, CURSOS, HABILIDADES, RESUMO, FIEL)
    _rodar({"texto_vaga": "vaga"}, llm)
    assert llm.pico >= 2


def test_painel_mostra_status():
    painel = Painel()
    painel.atualizar({"no": "experiencia", "status": "ok", "segundos": 3.2})
    assert painel.nos["experiencia"].status == "ok"
    assert painel.tabela().row_count == len(NOS)


def test_erro_num_agente_e_avisado_e_propagado():
    llm = _llm()
    del llm.respostas[type(RESUMO)]
    grafo = construir_grafo(BASE, CONFIG, I18N, dict.fromkeys(AGENTES, llm))
    eventos = []
    with pytest.raises(KeyError):
        for modo, dado in grafo.stream(
            {"texto_vaga": "v"}, stream_mode=["custom", "updates"]
        ):
            if modo == "custom":
                eventos.append(dado)
    assert {"no": "resumo", "status": "erro"}.items() <= next(
        e for e in eventos if e["no"] == "resumo" and e["status"] == "erro"
    ).items()


def test_fidelidade_nao_roda_se_as_regras_bloquearem():
    llm = _llm()
    llm.respostas[type(RESUMO)] = RESUMO.model_copy(
        update={"resumo": "Profissional com 10 anos de experiência em AWS."}
    )
    estado, eventos = _rodar({"texto_vaga": "vaga"}, llm)
    assert not estado["validacao"].aprovado
    assert "fidelidade" not in estado
    assert all(e["no"] != "validar_fidelidade" for e in eventos)
