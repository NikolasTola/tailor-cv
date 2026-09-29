"""LLM falsa para testes: devolve respostas prontas, sem rede e sem cota."""

from typing import Any

from pydantic import BaseModel


class LLMFalsa:
    def __init__(self, *respostas: BaseModel) -> None:
        self.respostas = {type(r): r for r in respostas}
        self.chamadas: list[list[Any]] = []

    def with_structured_output(
        self, schema: type[BaseModel], **_: Any
    ) -> "LLMFalsa._Runnable":
        return LLMFalsa._Runnable(self, schema)

    class _Runnable:
        def __init__(self, llm: "LLMFalsa", schema: type[BaseModel]) -> None:
            self.llm, self.schema = llm, schema

        def invoke(self, mensagens: list[Any]) -> BaseModel:
            self.llm.chamadas.append(mensagens)
            return self.llm.respostas[self.schema]
