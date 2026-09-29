from pathlib import Path

from llm_falsa import LLMFalsa

from tailor_cv.carregadores import carregar_base
from tailor_cv.schemas import Curriculo
from tailor_cv.schemas.agentes import ProblemaFidelidade, SaidaFidelidade
from tailor_cv.validacao import validar_fidelidade

RAIZ = Path(__file__).parent.parent
BASE = carregar_base(RAIZ / "exemplos" / "dados")
CV = Curriculo.model_validate_json(
    (RAIZ / "exemplos" / "curriculo.exemplo.json").read_text(encoding="utf-8")
)


def _problema(item: str, tipo: str) -> ProblemaFidelidade:
    return ProblemaFidelidade(item=item, tipo=tipo, trecho="x", explicacao="y")


def _validar(*problemas: ProblemaFidelidade):
    llm = LLMFalsa(SaidaFidelidade(problemas=list(problemas)))
    return validar_fidelidade(CV, BASE, llm), llm


def test_curriculo_fiel_passa():
    resultado, _ = _validar()
    assert resultado.aprovado and resultado.alertas == []


def test_itens_enviados_tem_texto_e_origem_em_ingles():
    _, llm = _validar()
    humano = llm.chamadas[0][1].content
    assert (
        '"id": "exp:empresa-alfa:cargo"' in humano
        and '"origem": "AI Engineer"' in humano
    )
    assert "30% reduction in monthly Bedrock spend" in humano  # a métrica vai junto
    assert '"ECS Fargate"' in humano  # as tags de tecnologia também
    assert '"id": "formacao:estatistica"' in humano
    assert '"id": "habilidade:Communication"' in humano
    assert (
        '"id": "habilidade:Python"' not in humano
    )  # técnica: não há tradução a checar
    assert '"id": "resumo"' in humano


def test_inflacao_bloqueia_e_aponta_o_agente():
    resultado, _ = _validar(_problema("exp:empresa-alfa:bullet:1", "inflacao"))
    [p] = resultado.bloqueios
    assert (p.agente, p.verificacao) == ("experiencia", "inflacao")


def test_problema_no_resumo_e_atribuido_ao_resumo():
    resultado, _ = _validar(_problema("resumo", "sem_lastro"))
    assert resultado.bloqueios[0].agente == "resumo"


def test_forma_verbal_e_termo_traduzido_sao_alertas():
    resultado, _ = _validar(
        _problema("exp:empresa-alfa:bullet:0", "forma_verbal"),
        _problema("habilidade:Communication", "termo_traduzido"),
    )
    assert resultado.aprovado
    assert [p.agente for p in resultado.alertas] == ["experiencia", "habilidades"]


def test_item_inventado_pelo_validador_e_ignorado():
    resultado, _ = _validar(_problema("exp:empresa-gama:bullet:0", "inflacao"))
    assert resultado.aprovado
