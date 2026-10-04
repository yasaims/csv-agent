import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from csv_agent.eval_records import BASELINE_FILE, check, fingerprint, record_run, update_baseline


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "cases.json").write_text("[]", encoding="utf-8")
    return tmp_path


def _run(accuracy: float, model: str = "m") -> dict[str, Any]:
    return {"models": {model: {"passed": int(accuracy * 10), "total": 10, "accuracy": accuracy}}}


def _recorded(**fields: Any) -> dict[str, Any]:
    return {"cases_hash": "c", "fingerprint": "f", "recorded_at": "t"} | fields


def test_fingerprint_ignores_line_endings_but_not_content(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_bytes(b"x\r\ny\r\n")
    crlf = fingerprint(tmp_path, [Path("a.txt")])
    (tmp_path / "a.txt").write_bytes(b"x\ny\n")
    lf = fingerprint(tmp_path, [Path("a.txt")])
    (tmp_path / "a.txt").write_bytes(b"x\nz\n")

    assert crlf == lf != fingerprint(tmp_path, [Path("a.txt")])


def test_update_baseline_registers_only_missing_models_unless_reset() -> None:
    existing = {"m": {"accuracy": 0.9}}
    run = _recorded(models=_run(0.5)["models"] | _run(0.7, "new")["models"])

    registered, changes = update_baseline(existing, run, "r1")
    reset, reset_changes = update_baseline(existing, run, "r1", reset_reason="new rules")

    assert registered["m"] == {"accuracy": 0.9}
    assert registered["new"]["source"] == "initial" and [c.model for c in changes] == ["new"]
    assert reset["m"]["accuracy"] == 0.5 and reset["m"]["reason"] == "new rules"
    assert {c.model for c in reset_changes} == {"m", "new"}


def test_check_warns_when_no_run_matches_current_code(repo: Path) -> None:
    record_run(repo, _run(0.9), repo / "evals" / "cases.json")
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")

    report = check(repo, base_baseline=None)

    assert report.run_id is None
    assert "No evaluation recorded" in report.warnings[0]


def test_check_flags_regression_beyond_tolerance_and_reports_baseline_changes(repo: Path) -> None:
    record_run(repo, _run(0.8), repo / "evals" / "cases.json")
    baseline = json.loads((repo / BASELINE_FILE).read_text(encoding="utf-8"))
    baseline["m"]["accuracy"] = 0.9
    (repo / BASELINE_FILE).write_text(json.dumps(baseline), encoding="utf-8")

    within = check(repo, base_baseline=None, tolerance=0.1)
    beyond = check(repo, base_baseline={}, tolerance=0.05)

    assert not within.models[0].regression
    assert beyond.models[0].regression
    assert [c.model for c in beyond.baseline_changes] == ["m"]
    assert beyond.baseline_changes[0].previous is None
