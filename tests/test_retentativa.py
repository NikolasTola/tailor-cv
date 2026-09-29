import pytest

from tailor_cv.llm import ComRetentativa, descrever_erro, erro_passageiro


class ErroDoProvedor(Exception):
    pass


SOBRECARGA = ErroDoProvedor("503 UNAVAILABLE. This model is experiencing high demand.")
CHAVE_INVALIDA = ErroDoProvedor("400 API key not valid.")


class ModeloInstavel:
    """Falha com `erro` nas primeiras `falhas` chamadas e depois responde."""

    def __init__(self, falhas: int, erro: Exception) -> None:
        self.falhas, self.erro, self.chamadas = falhas, erro, 0

    def with_structured_output(self, schema, **_):
        modelo = self

        class Runnable:
            def invoke(self, _mensagens):
                modelo.chamadas += 1
                if modelo.chamadas <= modelo.falhas:
                    raise modelo.erro
                return "ok"

        return Runnable()


def _com_retentativa(modelo, esperas: list[float]) -> ComRetentativa:
    return ComRetentativa(
        modelo, tentativas=4, espera_inicial=2.0, dormir=esperas.append
    )


def test_erro_passageiro_e_repetido_ate_funcionar():
    modelo, esperas = ModeloInstavel(2, SOBRECARGA), []
    resposta = _com_retentativa(modelo, esperas).with_structured_output(str).invoke([])
    assert resposta == "ok"
    assert modelo.chamadas == 3
    assert 2 <= esperas[0] < 3 and 4 <= esperas[1] < 5  # espera crescente


def test_desiste_depois_do_limite_de_tentativas():
    modelo, esperas = ModeloInstavel(10, SOBRECARGA), []
    with pytest.raises(ErroDoProvedor):
        _com_retentativa(modelo, esperas).with_structured_output(str).invoke([])
    assert modelo.chamadas == 4
    assert len(esperas) == 3


def test_erro_definitivo_falha_na_hora():
    modelo, esperas = ModeloInstavel(1, CHAVE_INVALIDA), []
    with pytest.raises(ErroDoProvedor):
        _com_retentativa(modelo, esperas).with_structured_output(str).invoke([])
    assert modelo.chamadas == 1
    assert esperas == []


@pytest.mark.parametrize(
    ("mensagem", "passageiro"),
    [
        ("503 UNAVAILABLE", True),
        ("429 RESOURCE_EXHAUSTED: quota", True),
        ("500 INTERNAL", True),
        ("404 NOT_FOUND: model not found", False),
        ("400 API key not valid", False),
    ],
)
def test_classificacao_dos_erros(mensagem, passageiro):
    assert erro_passageiro(ErroDoProvedor(mensagem)) is passageiro


def test_mensagens_para_a_usuaria():
    assert "Aguarde alguns minutos" in descrever_erro(SOBRECARGA)
    assert "Confira as chaves" in descrever_erro(CHAVE_INVALIDA)


COTA_DIARIA = ErroDoProvedor(
    "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: generate_content_free_tier_requests, "
    "limit: 20, model: gemini-3.7-flash\nPlease retry in 59.87s. "
    "'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'"
)
LIMITE_POR_MINUTO = ErroDoProvedor(
    "429 RESOURCE_EXHAUSTED. 'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel'. "
    "Please retry in 12.5s."
)


def test_cota_diaria_nao_e_repetida():
    modelo, esperas = ModeloInstavel(1, COTA_DIARIA), []
    with pytest.raises(ErroDoProvedor):
        _com_retentativa(modelo, esperas).with_structured_output(str).invoke([])
    assert modelo.chamadas == 1  # cada tentativa gastaria mais cota
    assert esperas == []


def test_limite_por_minuto_espera_o_tempo_pedido():
    modelo, esperas = ModeloInstavel(1, LIMITE_POR_MINUTO), []
    assert (
        _com_retentativa(modelo, esperas).with_structured_output(str).invoke([]) == "ok"
    )
    assert 12.5 <= esperas[0] < 13.5


def test_espera_pedida_longa_demais_desiste():
    erro = ErroDoProvedor("503 UNAVAILABLE. Please retry in 600s.")
    modelo, esperas = ModeloInstavel(1, erro), []
    with pytest.raises(ErroDoProvedor):
        _com_retentativa(modelo, esperas).with_structured_output(str).invoke([])
    assert esperas == []


def test_mensagem_de_cota_diaria_cita_o_modelo():
    mensagem = descrever_erro(COTA_DIARIA)
    assert "cota diária" in mensagem and "gemini-3.7-flash" in mensagem
