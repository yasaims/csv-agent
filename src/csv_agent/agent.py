from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

import ollama
from ollama import ChatResponse, Message

from csv_agent.table import Table
from csv_agent.tools import CsvTools

DEFAULT_MODEL = "qwen3.5:9b"

SYSTEM_PROMPT = """You are a data assistant that answers questions about a single CSV file.
Answer only from data returned by your tools. Never invent rows or values.
- Use search_rows to find rows by keywords (names, categories, descriptions).
- Use filter_rows to list every row meeting an exact condition (e.g. stock == 0, price > 10000).
- Use aggregate for exact counts, sums, averages, minimums and maximums. Do not do arithmetic yourself.
- Mention the row numbers you relied on.
- If the data does not contain the answer, say so.
- Reply in the same language as the user.

CSV schema:
{schema}"""


class ChatClient(Protocol):
    def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any] | Message],
        tools: Sequence[Callable[..., Any]],
        think: bool,
    ) -> ChatResponse: ...


ToolCallback = Callable[[str, dict[str, Any], str], None]


class AgentStepLimitError(RuntimeError):
    pass


class CsvAgent:
    def __init__(
        self,
        table: Table,
        client: ChatClient | None = None,
        model: str = DEFAULT_MODEL,
        think: bool = False,
        max_steps: int = 8,
        on_tool_call: ToolCallback | None = None,
    ) -> None:
        self._tools = CsvTools(table)
        self._client: ChatClient = client or ollama.Client()
        self._model = model
        self._think = think
        self._max_steps = max_steps
        self._on_tool_call = on_tool_call
        self._system_prompt = SYSTEM_PROMPT.format(schema=self._tools.get_schema())
        self._context_tokens = 0
        self._messages: list[Mapping[str, Any] | Message] = []
        self.reset()

    def reset(self) -> None:
        """Forget the conversation and start over from the system prompt."""
        self._context_tokens = 0
        self._messages = [{"role": "system", "content": self._system_prompt}]

    @property
    def context_tokens(self) -> int:
        """Tokens the model processed in the last chat call: the current conversation size."""
        return self._context_tokens

    def ask(self, question: str) -> str:
        self._messages.append({"role": "user", "content": question})
        for _ in range(self._max_steps):
            response = self._client.chat(
                model=self._model, messages=self._messages, tools=self._tools.functions, think=self._think
            )
            self._context_tokens = (response.prompt_eval_count or 0) + (response.eval_count or 0)
            message = response.message
            self._messages.append(message)
            if not message.tool_calls:
                return message.content or ""
            for call in message.tool_calls:
                arguments = dict(call.function.arguments)
                result = self._tools.call(call.function.name, arguments)
                if self._on_tool_call:
                    self._on_tool_call(call.function.name, arguments, result)
                self._messages.append({"role": "tool", "tool_name": call.function.name, "content": result})
        raise AgentStepLimitError(f"No final answer within {self._max_steps} steps")
