"""Run a fixed set of questions against several models and compare accuracy, latency and tool usage."""

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import ollama

from csv_agent.agent import AgentStepLimitError, ChatClient, CsvAgent
from csv_agent.eval_records import record_run, repo_root
from csv_agent.table import Table


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    # Every keyword must appear in the answer (thousands separators are ignored).
    expected: list[str]
    # Tools the agent is expected to call at least once; used only for reporting.
    expected_tools: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvalResult:
    model: str
    case_id: str
    run: int
    passed: bool
    answer: str
    error: str | None
    seconds: float
    tools_called: list[str]
    used_expected_tools: bool


def load_cases(path: str | Path) -> list[EvalCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvalCase(**item) for item in data]


def _normalize(text: str) -> str:
    return re.sub(r"[,，]", "", text)


def is_correct(answer: str, expected: Sequence[str]) -> bool:
    normalized = _normalize(answer)
    return all(_normalize(keyword) in normalized for keyword in expected)


def run_case(
    table: Table, case: EvalCase, model: str, run: int, client: ChatClient | None = None, think: bool = False
) -> EvalResult:
    tools_called: list[str] = []
    agent = CsvAgent(
        table, client=client, model=model, think=think, on_tool_call=lambda name, _a, _r: tools_called.append(name)
    )
    answer, error = "", None
    start = time.perf_counter()
    try:
        answer = agent.ask(case.question)
    except (ConnectionError, AgentStepLimitError, ollama.ResponseError) as e:
        error = str(e)
    seconds = time.perf_counter() - start
    return EvalResult(
        model=model,
        case_id=case.id,
        run=run,
        passed=error is None and is_correct(answer, case.expected),
        answer=answer,
        error=error,
        seconds=seconds,
        tools_called=tools_called,
        used_expected_tools=set(case.expected_tools) <= set(tools_called),
    )


@dataclass(frozen=True)
class ModelSummary:
    passed: int
    total: int
    accuracy: float
    tool_ok: int
    errors: int
    avg_seconds: float
    avg_tools: float


def summarize_by_model(results: Sequence[EvalResult]) -> dict[str, ModelSummary]:
    summaries: dict[str, ModelSummary] = {}
    for model in dict.fromkeys(r.model for r in results):
        rs = [r for r in results if r.model == model]
        n = len(rs)
        passed = sum(r.passed for r in rs)
        summaries[model] = ModelSummary(
            passed=passed,
            total=n,
            accuracy=passed / n,
            tool_ok=sum(r.used_expected_tools for r in rs),
            errors=sum(r.error is not None for r in rs),
            avg_seconds=sum(r.seconds for r in rs) / n,
            avg_tools=sum(len(r.tools_called) for r in rs) / n,
        )
    return summaries


def summarize(results: Sequence[EvalResult]) -> str:
    header = f"{'model':<24} {'accuracy':>10} {'tool use':>10} {'errors':>7} {'avg sec':>8} {'avg tools':>10}"
    lines = [header, "-" * len(header)]
    for model, s in summarize_by_model(results).items():
        lines.append(
            f"{model:<24} {f'{s.passed}/{s.total}':>10} {f'{s.tool_ok}/{s.total}':>10} {s.errors:>7}"
            f" {s.avg_seconds:>8.1f} {s.avg_tools:>10.1f}"
        )
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Ollama models on a set of CSV questions.")
    parser.add_argument("csv", help="Path to the CSV file")
    parser.add_argument("cases", help="Path to a JSON file with evaluation cases")
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model names to compare")
    parser.add_argument("--repeats", type=int, default=1, help="Runs per case and model (default: 1)")
    parser.add_argument("--think", action="store_true", help="Enable the models' thinking mode")
    parser.add_argument("-o", "--output", help="Write every result as JSON Lines to this path")
    parser.add_argument(
        "--record", action="store_true", help="Save the run under evals/records and register missing baselines"
    )
    parser.add_argument(
        "--reset-baseline",
        metavar="REASON",
        help="Save the run and make it the baseline of every evaluated model (implies --record)",
    )
    args = parser.parse_args(argv)
    if args.reset_baseline is not None and not args.reset_baseline.strip():
        parser.error("--reset-baseline needs a non-empty reason")
    return args


def _record(args: argparse.Namespace, results: Sequence[EvalResult]) -> int:
    summaries = summarize_by_model(results)
    unavailable = [model for model, s in summaries.items() if s.errors == s.total]
    if unavailable:
        print(f"Not recorded: every run failed for {', '.join(unavailable)}", file=sys.stderr)
        return 1
    run = {
        "csv": Path(args.csv).as_posix(),
        "cases": Path(args.cases).as_posix(),
        "repeats": args.repeats,
        "think": args.think,
        "models": {model: asdict(s) for model, s in summaries.items()},
        "results": [asdict(r) for r in results],
    }
    try:
        path, changes = record_run(repo_root(), run, Path(args.cases), args.reset_baseline)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"Failed to record the run: {e}", file=sys.stderr)
        return 1
    print(f"Recorded {path}")
    for change in changes:
        print(change.describe())
    return 0


def main(argv: Sequence[str] | None = None, client: ChatClient | None = None) -> int:
    args = _parse_args(argv)
    try:
        table = Table.from_csv(args.csv)
        cases = load_cases(args.cases)
    except (OSError, ValueError, TypeError) as e:
        print(f"Failed to load inputs: {e}", file=sys.stderr)
        return 1

    results: list[EvalResult] = []
    for model in args.models:
        for case in cases:
            for run in range(args.repeats):
                result = run_case(table, case, model, run, client=client, think=args.think)
                results.append(result)
                mark = "PASS" if result.passed else "FAIL"
                print(f"[{mark}] {model} {case.id}#{run} ({result.seconds:.1f}s)", file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            for result in results:
                record: dict[str, Any] = asdict(result)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(summarize(results))
    if args.record or args.reset_baseline is not None:
        return _record(args, results)
    return 0
