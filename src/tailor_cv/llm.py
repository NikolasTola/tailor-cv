"""Criação dos modelos de LLM a partir das strings do config.yaml.

Trocar de provedor é só mudar a string: "google_genai:...", "groq:...",
"anthropic:...", "openai:...", "ollama:...". Nenhum agente depende de um
provedor específico.
"""

import random
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

from langchain.chat_models import init_chat_model

# Trechos que aparecem nas mensagens de erro passageiro dos provedores:
# sobrecarga (503), limite por minuto (429) e falha interna (500).
SINAIS_PASSAGEIROS = (
    "503",
    "UNAVAILABLE",
    "overloaded",
    "high demand",
    "429",
    "RESOURCE_EXHAUSTED",
    "rate limit",
    "500",
    "INTERNAL",
)


class ModeloEstruturado(Protocol):
    """O que um agente precisa de uma LLM: saída estruturada num schema Pydantic.

    Nos testes, um modelo falso implementa este mesmo contrato.
    """

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any: ...


ESPERA_MAXIMA = 90.0  # segundos; acima disso não vale a pena esperar


def cota_diaria(exc: BaseException) -> bool:
    """Cota do dia esgotada: tentar de novo só gasta mais requisições."""
    texto = str(exc)
    return "PerDay" in texto or "per day" in texto.lower()


def erro_passageiro(exc: BaseException) -> bool:
    if cota_diaria(exc):
        return False
    texto = f"{type(exc).__name__} {exc}"
    return any(sinal.lower() in texto.lower() for sinal in SINAIS_PASSAGEIROS)


def espera_sugerida(exc: BaseException) -> float | None:
    """Tempo que o provedor pede para esperar ("retry in 59.8s" ou "retryDelay: 59s")."""
    texto = str(exc)
    achado = re.search(r"retry in (\d+(?:\.\d+)?)s", texto) or re.search(
        r"retryDelay'?\"?:\s*'?\"?(\d+(?:\.\d+)?)s", texto
    )
    return float(achado[1]) if achado else None


class ComRetentativa:
    """Envolve um modelo e repete a chamada em erros passageiros, com espera crescente.

    Erros definitivos (chave inválida, modelo inexistente) falham na hora.
    """

    def __init__(
        self,
        modelo: ModeloEstruturado,
        tentativas: int = 4,
        espera_inicial: float = 2.0,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.modelo = modelo
        self.tentativas = tentativas
        self.espera_inicial = espera_inicial
        self.dormir = dormir

    def with_structured_output(self, schema: Any, **kwargs: Any) -> "_Chamada":
        return _Chamada(self, self.modelo.with_structured_output(schema, **kwargs))


class _Chamada:
    def __init__(self, dono: ComRetentativa, runnable: Any) -> None:
        self.dono, self.runnable = dono, runnable

    def invoke(self, mensagens: Any) -> Any:
        for tentativa in range(1, self.dono.tentativas + 1):
            try:
                return self.runnable.invoke(mensagens)
            except Exception as exc:
                if tentativa == self.dono.tentativas or not erro_passageiro(exc):
                    raise
                # 2s, 4s, 8s... ou o tempo que o provedor pedir, se for maior;
                # a aleatoriedade evita que os agentes paralelos tentem todos juntos
                espera = self.dono.espera_inicial * 2 ** (tentativa - 1)
                pedida = espera_sugerida(exc)
                if pedida is not None:
                    if pedida > ESPERA_MAXIMA:
                        raise
                    espera = max(espera, pedida)
                self.dono.dormir(espera + random.uniform(0, 1))
        raise AssertionError("inalcançável")


def criar_llm(modelo: str) -> ComRetentativa:
    # Sem temperatura: os modelos Gemini 3.x não aceitam mais esse parâmetro,
    # e cada provedor já tem um padrão adequado.
    return ComRetentativa(init_chat_model(modelo))


def descrever_erro(exc: BaseException) -> str:
    """Mensagem para a pessoa usuária, com o que fazer em cada caso."""
    if cota_diaria(exc):
        modelo = re.search(r"model: ([\w.\-]+)", str(exc))
        nome = f" do modelo {modelo[1]}" if modelo else ""
        return (
            f"A cota diária gratuita{nome} acabou.\n"
            "Ela é renovada uma vez por dia. Até lá, troque esse modelo no config.yaml "
            "por outro: cada modelo tem a sua própria cota.\n"
            f"Detalhes do provedor: {exc}"
        )
    if erro_passageiro(exc):
        return (
            f"O provedor da LLM está indisponível ou no limite de uso: {exc}\n"
            "Já tentamos de novo algumas vezes. Aguarde alguns minutos e rode outra vez, "
            "ou troque temporariamente o modelo no config.yaml."
        )
    return (
        f"Falha ao chamar a LLM: {exc}\n"
        "Confira as chaves no .env e os nomes dos modelos no config.yaml."
    )
