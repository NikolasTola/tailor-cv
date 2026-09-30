"""LLM falsa para testes: devolve respostas prontas, sem rede e sem cota."""

from typing import Any

from pydantic import BaseModel


class LLMFalsa:
    """Uma resposta por schema. Para simular correções, passe uma lista com a
    sequência de respostas daquele schema: cada chamada consome a próxima, e a
    última se repete."""

    def __init__(self, *respostas: BaseModel | list[BaseModel]) -> None:
        self.respostas: dict[type, Any] = {}
        for r in respostas:
            chave = type(r[0]) if isinstance(r, list) else type(r)
            self.respostas[chave] = r
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
            resposta = self.llm.respostas[self.schema]
            if isinstance(resposta, list):
                return resposta.pop(0) if len(resposta) > 1 else resposta[0]
            return resposta
