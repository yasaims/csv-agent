"""Store evaluation runs in the repository and compare them with per-model baseline accuracies."""

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RECORDS_DIR = Path("evals/records")
RUNS_DIR = RECORDS_DIR / "runs"
BASELINE_FILE = RECORDS_DIR / "baseline.json"
# Inputs that can change evaluation outcomes. Tests, docs and CI files are left out on purpose.
FINGERPRINT_PATHS = ("src", "data", "evals", "uv.lock")
DEFAULT_TOLERANCE = 0.05


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def repo_root() -> Path:
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())


def tracked_files(root: Path) -> list[Path]:
    """Files under FINGERPRINT_PATHS that git tracks or would track (untracked but not ignored)."""
    out = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *FINGERPRINT_PATHS)
    files = {Path(name) for name in out.split("\0") if name}
    return sorted(f for f in files if RECORDS_DIR not in f.parents and (root / f).is_file())


def _normalized_bytes(path: Path) -> bytes:
    # Windows checkouts may use CRLF while CI uses LF; both must hash the same.
    return path.read_bytes().replace(b"\r\n", b"\n")


def file_hash(path: Path) -> str:
    return hashlib.sha256(_normalized_bytes(path)).hexdigest()


def fingerprint(root: Path, files: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for name in sorted(Path(f).as_posix() for f in files):
        content = _normalized_bytes(root / name)
        digest.update(f"{name}\0{len(content)}\0".encode())
        digest.update(content)
    return digest.hexdigest()


def current_fingerprint(root: Path) -> str:
    return fingerprint(root, tracked_files(root))


def _git_head(root: Path) -> str | None:
    try:
        return _git(root, "rev-parse", "HEAD").strip()
    except subprocess.CalledProcessError:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _format_score(entry: dict[str, Any]) -> str:
    return f"{entry['passed']}/{entry['total']} ({entry['accuracy']:.1%})"


@dataclass(frozen=True)
class BaselineChange:
    model: str
    previous: dict[str, Any] | None
    current: dict[str, Any]

    def describe(self) -> str:
        if self.previous is None:
            return f"Baseline registered: {self.model} {_format_score(self.current)}"
        return (
            f"Baseline RESET: {self.model} {_format_score(self.previous)} -> {_format_score(self.current)}"
            f" (reason: {self.current.get('reason') or 'not recorded'})"
        )


def update_baseline(
    baseline: dict[str, Any], run: dict[str, Any], run_id: str, reset_reason: str | None = None
) -> tuple[dict[str, Any], list[BaselineChange]]:
    """Register the run as baseline for models without one, or for every model in the run when resetting."""
    updated = dict(baseline)
    changes: list[BaselineChange] = []
    for model, summary in run["models"].items():
        previous = baseline.get(model)
        if previous is not None and reset_reason is None:
            continue
        entry = {
            "accuracy": summary["accuracy"],
            "passed": summary["passed"],
            "total": summary["total"],
            "cases_hash": run["cases_hash"],
            "fingerprint": run["fingerprint"],
            "recorded_at": run["recorded_at"],
            "run": run_id,
            "source": "reset" if reset_reason is not None else "initial",
            "reason": reset_reason,
        }
        updated[model] = entry
        changes.append(BaselineChange(model, previous, entry))
    return updated, changes


def diff_baselines(base: dict[str, Any], head: dict[str, Any]) -> list[BaselineChange]:
    return [BaselineChange(model, base.get(model), entry) for model, entry in head.items() if base.get(model) != entry]


def record_run(
    root: Path, run: dict[str, Any], cases_path: Path, reset_reason: str | None = None
) -> tuple[Path, list[BaselineChange]]:
    """Save `run` (models summary, results, settings) with provenance and update the baseline file."""
    recorded_at = datetime.now(UTC)
    run = {
        "recorded_at": recorded_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fingerprint": current_fingerprint(root),
        "git_head": _git_head(root),
        "cases_hash": file_hash(cases_path),
    } | run
    run_id = f"{recorded_at:%Y%m%dT%H%M%S%fZ}_{run['fingerprint'][:8]}"
    path = root / RUNS_DIR / f"{run_id}.json"
    _write_json(path, run)
    baseline, changes = update_baseline(_load_json(root / BASELINE_FILE), run, run_id, reset_reason)
    if changes:
        _write_json(root / BASELINE_FILE, baseline)
    return path, changes


@dataclass(frozen=True)
class ModelCheck:
    model: str
    current: dict[str, Any]
    baseline: dict[str, Any] | None
    regression: bool


@dataclass
class Report:
    fingerprint: str
    run_id: str | None = None
    models: list[ModelCheck] = field(default_factory=list)
    baseline_changes: list[BaselineChange] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _latest_run(root: Path, fp: str) -> tuple[str, dict[str, Any]] | None:
    # Run file names start with a UTC timestamp, so name order is chronological.
    for path in sorted((root / RUNS_DIR).glob("*.json"), reverse=True):
        run = _load_json(path)
        if run.get("fingerprint") == fp:
            return path.stem, run
    return None


def check(root: Path, base_baseline: dict[str, Any] | None, tolerance: float = DEFAULT_TOLERANCE) -> Report:
    baseline = _load_json(root / BASELINE_FILE)
    report = Report(fingerprint=current_fingerprint(root))
    if base_baseline is not None:
        report.baseline_changes = diff_baselines(base_baseline, baseline)

    latest = _latest_run(root, report.fingerprint)
    if latest is None:
        report.warnings.append(
            f"No evaluation recorded for this code state (fingerprint {report.fingerprint[:8]}). "
            "Run csv-agent-eval with --record and commit evals/records/."
        )
        return report
    report.run_id, run = latest

    for model, summary in run["models"].items():
        entry = baseline.get(model)
        # The small epsilon keeps a drop of exactly `tolerance` from counting as a regression.
        regression = entry is not None and summary["accuracy"] < entry["accuracy"] - tolerance - 1e-9
        report.models.append(ModelCheck(model, summary, entry, regression))
        if entry is None:
            report.warnings.append(f"No baseline for {model}.")
            continue
        if regression:
            report.warnings.append(
                f"Accuracy regression for {model}: {_format_score(summary)} vs baseline {_format_score(entry)}."
            )
        if entry["cases_hash"] != run["cases_hash"]:
            report.warnings.append(
                f"Evaluation cases changed since the {model} baseline was set; consider --reset-baseline."
            )
    return report


def render_markdown(report: Report, tolerance: float) -> str:
    lines = ["## Evaluation check", ""]
    if report.baseline_changes:
        lines += ["### :warning: Baseline changed in this PR", ""]
        lines += [f"- **{change.describe()}**" for change in report.baseline_changes]
        lines.append("")
    if report.run_id is not None:
        lines += [
            f"Run `{report.run_id}` matches this code state (tolerance {tolerance:.0%}).",
            "",
            "| model | accuracy | baseline | delta | status |",
            "| --- | --- | --- | --- | --- |",
        ]
        for m in report.models:
            if m.baseline is None:
                lines.append(f"| {m.model} | {_format_score(m.current)} | - | - | no baseline |")
                continue
            delta = m.current["accuracy"] - m.baseline["accuracy"]
            status = ":x: regression" if m.regression else "ok"
            lines.append(
                f"| {m.model} | {_format_score(m.current)} | {_format_score(m.baseline)} | {delta:+.1%} | {status} |"
            )
        lines.append("")
    if report.warnings:
        lines += ["### Warnings", ""] + [f"- {w}" for w in report.warnings] + [""]
    return "\n".join(lines)


def _annotations(report: Report) -> list[str]:
    lines = [f"::warning title=Evaluation::{w}" for w in report.warnings]
    for change in report.baseline_changes:
        level = "notice" if change.previous is None else "warning"
        lines.append(f"::{level} title=Evaluation baseline::{change.describe()}")
    return lines


def check_main(argv: Sequence[str] | None = None) -> int:
    """Report evaluation status for the current checkout. Never fails, so CI only informs."""
    parser = argparse.ArgumentParser(description="Check recorded evaluations against per-model baselines.")
    parser.add_argument("--base-baseline", type=Path, help="baseline.json of the target branch, to show changes")
    parser.add_argument(
        "--tolerance", type=float, default=DEFAULT_TOLERANCE, help="Allowed accuracy drop (default: 0.05)"
    )
    parser.add_argument("--summary", type=Path, help="Append the Markdown report to this file instead of stdout")
    args = parser.parse_args(argv)

    base = _load_json(args.base_baseline) if args.base_baseline else None
    report = check(repo_root(), base, args.tolerance)
    markdown = render_markdown(report, args.tolerance)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(markdown + "\n")
    else:
        print(markdown)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for line in _annotations(report):
            print(line)
    return 0
