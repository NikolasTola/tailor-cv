from pathlib import Path

from llm_falsa import LLMFalsa
from test_agentes_llm import ANALISE, _saida

from tailor_cv.agentes import dados_pessoais, idiomas, titulo_e_nome
from tailor_cv.agentes.experiencia import selecionar_experiencias
from tailor_cv.agentes.secoes import (
    escrever_resumo,
    evidencias,
    gerar_formacao,
    selecionar_cursos,
    selecionar_habilidades,
)
from tailor_cv.carregadores import carregar_base, carregar_i18n
from tailor_cv.config import carregar_config
from tailor_cv.schemas import Curriculo
from tailor_cv.schemas.agentes import (
    FormacaoGerada,
    HabilidadeEscolhida,
    SaidaCursos,
    SaidaFormacao,
    SaidaHabilidades,
    SaidaResumo,
)
from tailor_cv.schemas.curriculo import Cabecalho
from tailor_cv.schemas.origem import FormacaoOrigem
from tailor_cv.validacao import validar_regras

RAIZ = Path(__file__).parent.parent
BASE = carregar_base(RAIZ / "exemplos" / "dados")
I18N = carregar_i18n(RAIZ / "i18n_pt.yaml")
CONFIG = carregar_config(RAIZ / "config.yaml")

FORMACAO = SaidaFormacao(
    formacoes=[FormacaoGerada(origem="estatistica", curso="Bacharelado em Estatística")]
)
CURSOS = SaidaCursos(origens=["langgraph-agents", "aws-ml-specialty"])
HABILIDADES = SaidaHabilidades(
    habilidades=[
        HabilidadeEscolhida(origem="Communication", texto="Comunicação"),
        HabilidadeEscolhida(origem="Python", texto="Python"),
        HabilidadeEscolhida(origem="AWS Bedrock", texto="AWS Bedrock"),
        HabilidadeEscolhida(origem="RAG", texto="RAG"),
    ]
)
RESUMO = SaidaResumo(
    resumo="Profissional com experiência em IA generativa na AWS, com RAG em produção "
    "e AWS Bedrock.\n\nPossui vivência com Python e LangGraph."
)


def _experiencias():
    return selecionar_experiencias(ANALISE, BASE, CONFIG, I18N, LLMFalsa(_saida()))[0]


# ---------- Formação ----------


def test_formacao_traduzida_com_fatos_da_origem():
    [f] = gerar_formacao(BASE, LLMFalsa(FORMACAO))
    assert (f.curso, f.instituicao, f.conclusao) == (
        "Bacharelado em Estatística",
        "Universidade Exemplo",
        "2019",
    )


def test_formacao_esquecida_pela_llm_entra_com_nome_original_e_em_andamento():
    extra = FormacaoOrigem(
        id="mestrado",
        degree="Master's in Computer Science",
        institution="UFX",
        completion=2027,
        in_progress=True,
    )
    base = BASE.model_copy(update={"formacao": [*BASE.formacao, extra]})
    formacoes = gerar_formacao(base, LLMFalsa(FORMACAO))
    assert [f.origem for f in formacoes] == [
        "mestrado",
        "estatistica",
    ]  # mais recente primeiro
    assert formacoes[0].curso == "Master's in Computer Science"
    assert formacoes[0].conclusao == "2027 (previsão)"


def test_sem_formacao_nao_chama_llm():
    llm = LLMFalsa(FORMACAO)
    assert gerar_formacao(BASE.model_copy(update={"formacao": []}), llm) == []
    assert llm.chamadas == []


# ---------- Cursos ----------


def test_cursos_na_ordem_da_llm_com_fatos_da_origem():
    cursos = selecionar_cursos(ANALISE, BASE, CONFIG, LLMFalsa(CURSOS))
    assert [c.origem for c in cursos] == ["langgraph-agents", "aws-ml-specialty"]
    assert (cursos[1].nome, cursos[1].instituicao, cursos[1].ano) == (
        "AWS Certified Machine Learning – Specialty",
        "Amazon Web Services",
        "2024",
    )


def test_cursos_inventados_repetidos_e_acima_do_limite():
    saida = SaidaCursos(origens=["fantasma", "aws-ml-specialty", "aws-ml-specialty"])
    cursos = selecionar_cursos(ANALISE, BASE, CONFIG, LLMFalsa(saida))
    assert [c.origem for c in cursos] == ["aws-ml-specialty"]

    config = CONFIG.model_copy(
        update={"limites": CONFIG.limites.model_copy(update={"cursos_max": 1})}
    )
    assert len(selecionar_cursos(ANALISE, BASE, config, LLMFalsa(CURSOS))) == 1


# ---------- Habilidades ----------


def test_evidencias_vem_das_tags_selecionadas():
    ev = evidencias(_experiencias(), [], BASE)
    assert "AWS Bedrock" in ev and "Python" in ev
    assert "Power BI" not in ev  # beta-dash não foi selecionado


def test_habilidades_tecnicas_primeiro_e_nunca_traduzidas():
    saida = HABILIDADES.model_copy(deep=True)
    saida.habilidades[1].texto = "Píton"
    habilidades = selecionar_habilidades(
        ANALISE, _experiencias(), [], BASE, CONFIG, LLMFalsa(saida)
    )
    assert [h.texto for h in habilidades] == [
        "Python",
        "AWS Bedrock",
        "RAG",
        "Comunicação",
    ]


def test_habilidade_inventada_fica_de_fora():
    saida = SaidaHabilidades(
        habilidades=[
            HabilidadeEscolhida(origem="Kubernetes", texto="Kubernetes"),
            HabilidadeEscolhida(origem="Python", texto="Python"),
        ]
    )
    habilidades = selecionar_habilidades(ANALISE, [], [], BASE, CONFIG, LLMFalsa(saida))
    assert [h.origem for h in habilidades] == ["Python"]


def test_prompt_de_habilidades_recebe_as_evidencias():
    llm = LLMFalsa(HABILIDADES)
    selecionar_habilidades(ANALISE, _experiencias(), [], BASE, CONFIG, llm)
    humano = llm.chamadas[0][1].content
    assert "Tecnologias já selecionadas" in humano and "ECS Fargate" in humano


# ---------- Resumo ----------


def test_resumo_normaliza_espacos():
    resumo = escrever_resumo(ANALISE, _experiencias(), [], [], CONFIG, LLMFalsa(RESUMO))
    assert "\n" not in resumo and "  " not in resumo


# ---------- Integração: todos os agentes juntos passam no validador ----------


def test_curriculo_montado_por_todos_os_agentes_passa_nas_regras():
    experiencias = _experiencias()
    formacao = gerar_formacao(BASE, LLMFalsa(FORMACAO))
    cursos = selecionar_cursos(ANALISE, BASE, CONFIG, LLMFalsa(CURSOS))
    habilidades = selecionar_habilidades(
        ANALISE, experiencias, cursos, BASE, CONFIG, LLMFalsa(HABILIDADES)
    )
    resumo = escrever_resumo(
        ANALISE, experiencias, habilidades, formacao, CONFIG, LLMFalsa(RESUMO)
    )
    cv = Curriculo(
        cabecalho=Cabecalho(
            **titulo_e_nome(BASE.perfil, ANALISE.headline),
            **dados_pessoais(BASE.perfil),
        ),
        resumo=resumo,
        experiencias=experiencias,
        formacao=formacao,
        cursos=cursos,
        habilidades=habilidades,
        idiomas=idiomas(BASE.idiomas, I18N),
    )
    resultado = validar_regras(cv, BASE, I18N, CONFIG)
    assert resultado.aprovado, resultado.bloqueios
