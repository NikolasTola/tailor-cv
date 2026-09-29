"""Criação dos modelos de LLM a partir das strings do config.yaml.

Trocar de provedor é só mudar a string: "google_genai:...", "groq:...",
"anthropic:...", "openai:...", "ollama:...". Nenhum agente depende de um
provedor específico.
"""

from typing import Any, Protocol

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


class ModeloEstruturado(Protocol):
    """O que um agente precisa de uma LLM: saída estruturada num schema Pydantic.

    Nos testes, um modelo falso implementa este mesmo contrato.
    """

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any: ...


def criar_llm(modelo: str) -> BaseChatModel:
    # Sem temperatura: os modelos Gemini 3.x não aceitam mais esse parâmetro,
    # e cada provedor já tem um padrão adequado.
    return init_chat_model(modelo)
