import argparse
import sys
from collections.abc import Sequence
from typing import Any

from csv_agent.agent import DEFAULT_MODEL, AgentStepLimitError, ChatClient, CsvAgent
from csv_agent.table import Table

EXIT_COMMANDS = {"exit", "quit"}


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask questions about a CSV file using a local Ollama model.")
    parser.add_argument("csv", help="Path to the CSV file")
    parser.add_argument("question", nargs="?", help="Question to ask. Starts an interactive session when omitted.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--think", action="store_true", help="Enable the model's thinking mode")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print tool calls to stderr")
    return parser.parse_args(argv)


def _print_tool_call(name: str, arguments: dict[str, Any], result: str) -> None:
    print(f"[tool] {name}({arguments}) -> {result}", file=sys.stderr)


def _interactive(agent: CsvAgent) -> None:
    while True:
        try:
            question = input("> ").strip()
        except EOFError:
            return
        if question in EXIT_COMMANDS:
            return
        if not question:
            continue
        try:
            print(agent.ask(question))
        except AgentStepLimitError as e:
            print(e, file=sys.stderr)


def main(argv: Sequence[str] | None = None, client: ChatClient | None = None) -> int:
    args = _parse_args(argv)
    try:
        table = Table.from_csv(args.csv)
    except (OSError, ValueError) as e:
        print(f"Failed to load CSV: {e}", file=sys.stderr)
        return 1

    agent = CsvAgent(
        table,
        client=client,
        model=args.model,
        think=args.think,
        on_tool_call=_print_tool_call if args.verbose else None,
    )
    try:
        if args.question:
            print(agent.ask(args.question))
        else:
            _interactive(agent)
    except (ConnectionError, AgentStepLimitError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
