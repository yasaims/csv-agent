from typing import Any

from ollama import ChatResponse, Message


def answer(content: str) -> ChatResponse:
    return ChatResponse(message=Message(role="assistant", content=content))


def tool_call(name: str, arguments: dict[str, Any]) -> ChatResponse:
    call = Message.ToolCall(function=Message.ToolCall.Function(name=name, arguments=arguments))
    return ChatResponse(message=Message(role="assistant", content="", tool_calls=[call]))


class ScriptedClient:
    """Returns prepared responses (or raises prepared exceptions) in order and records every chat request."""

    def __init__(self, *responses: ChatResponse | Exception) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def chat(self, **kwargs: Any) -> ChatResponse:
        # Copy messages because the agent keeps appending to the same list.
        self.requests.append(kwargs | {"messages": list(kwargs["messages"])})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
