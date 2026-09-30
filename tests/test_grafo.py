import threading
import time
from pathlib import Path

import pytest
from llm_falsa import LLMFalsa
from test_agentes_llm import ANALISE, _saida
from test_agentes_secoes import CURSOS, FORMACAO, HABILIDADES, PROJETOS, RESUMO

from tailor_cv.carregadores import carregar_base, carregar_i18n
from tailor_cv.config import carregar_config
from tailor_cv.grafo import NOS, _pode_corrigir, construir_grafo
from tailor_cv.painel import Painel
from tailor_cv.schemas.agentes import AvaliacaoFidelidade, SaidaFidelidade
from tailor_cv.validacao import Problema, ResultadoValidacao

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
    "projetos",
)
FIEL = SaidaFidelidade(avaliacoes=[])


def _llm() -> LLMFalsa:
    # uma única LLM falsa responde a todos: ela escolhe a resposta pelo schema
    return LLMFalsa(
        ANALISE, _saida(), FORMACAO, CURSOS, HABILIDADES, RESUMO, FIEL, PROJETOS
    )


def _rodar(entrada: dict, llm: LLMFalsa | None = None) -> tuple[dict, list[dict]]:
    llm = llm or _llm()
    grafo = construir_grafo(BASE, CONFIG, I18N, dict.fromkeys(AGENTES, llm))
    estado, eventos = dict(entrada), []
    for modo, dado in grafo.stream(entrada, stream_mode=["custom", "values"]):
        if modo == "custom":
            eventos.append(dado)
        else:
            estado = dado
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
    assert finais == {nome: "ok" for nome, _ in NOS if nome != "corrigir"}


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
    llm = LLMLenta(
        ANALISE, _saida(), FORMACAO, CURSOS, HABILIDADES, RESUMO, FIEL, PROJETOS
    )
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
    assert estado.get("fidelidade") is None
    assert all(e["no"] != "validar_fidelidade" for e in eventos)


# ---------- Correções automáticas ----------

RESUMO_RUIM = RESUMO.model_copy(
    update={"resumo": "Profissional com 10 anos de experiência em AWS."}
)


def test_bloqueio_nas_regras_e_corrigido_na_retentativa():
    llm = _llm()
    llm.respostas[type(RESUMO)] = [RESUMO_RUIM, RESUMO]
    estado, _ = _rodar({"texto_vaga": "vaga"}, llm)
    assert estado["validacao"].aprovado and estado["fidelidade"].aprovado
    [h] = estado["historico"]
    assert h["refeitos"] == ["resumo"]  # só o agente culpado
    assert "10" in h["bloqueios"][0]
    # a nova chamada do Resumo recebeu o problema no prompt
    ultima_do_resumo = [c for c in llm.chamadas if "agente de Resumo" in c[0].content][
        -1
    ]
    assert "Na tentativa anterior" in ultima_do_resumo[1].content


def test_bloqueio_na_experiencia_refaz_os_dependentes():
    llm = _llm()
    fidelidade_ruim = SaidaFidelidade(
        avaliacoes=[
            AvaliacaoFidelidade(
                item="exp:empresa-alfa:bullet:1",
                veredito="inflacao",
                trecho="30%",
                comparacao="escopo ampliado",
            )
        ]
    )
    llm.respostas[SaidaFidelidade] = [fidelidade_ruim, FIEL]
    estado, _ = _rodar({"texto_vaga": "vaga"}, llm)
    assert estado["fidelidade"].aprovado
    assert estado["historico"][0]["refeitos"] == [
        "experiencia",
        "habilidades",
        "resumo",
    ]


def test_desiste_depois_do_limite_de_retentativas():
    llm = _llm()
    llm.respostas[type(RESUMO)] = RESUMO_RUIM
    estado, _ = _rodar({"texto_vaga": "vaga"}, llm)
    assert not estado["validacao"].aprovado
    assert len(estado["historico"]) == CONFIG.limites.retentativas_max
    assert estado.get("fidelidade") is None


def test_bloqueio_de_agente_de_regra_nao_e_retentado():
    estado = {
        "validacao": ResultadoValidacao(
            bloqueios=[Problema("dados_pessoais", "divergente", "cabecalho.email", "x")]
        ),
        "tentativas": 0,
    }
    assert not _pode_corrigir(estado, CONFIG)


def test_sem_retentativas_configuradas():
    lim = CONFIG.limites.model_copy(update={"retentativas_max": 0})
    config = CONFIG.model_copy(update={"limites": lim})
    llm = _llm()
    llm.respostas[type(RESUMO)] = [RESUMO_RUIM, RESUMO]
    grafo = construir_grafo(BASE, config, I18N, dict.fromkeys(AGENTES, llm))
    estado = grafo.invoke({"texto_vaga": "vaga"})
    assert not estado["validacao"].aprovado
    assert estado.get("historico", []) == []
