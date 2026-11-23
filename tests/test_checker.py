# tests/test_checker.py
# Checker self-test on the committed sample run (runs/sample_S3, a real S3 run): the unmodified run must pass,
# and each known corruption of a temporary copy (drop / swap / change value / delay / double winner) must be
# flagged by the invariant it violates. Proves the consistency checker can actually fail.
# Serves N3.
"""Self-test of harness.checker on a real run."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import checker

SAMPLE = Path(__file__).resolve().parent.parent / "runs" / "sample_S3"


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample run not present")
def test_sample_run_passes_all_invariants() -> None:
    """The real S3 run satisfies I1-I6."""
    results = checker.check_run(checker.RunData.load(SAMPLE))
    assert checker.overall(results) == "PASS", [r.detail for r in results if r.status == "FAIL"]
    assert {r.invariant for r in results if r.status == "PASS"} == {"I1", "I2", "I3", "I4", "I5", "I6"}


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample run not present")
def test_checker_flags_every_corruption() -> None:
    """Each corruption is detected by its invariant (and the baseline is clean)."""
    ok, rows = checker.self_test(SAMPLE)
    assert len(rows) == 1 + len(checker.SELF_TEST_CASES)
    assert ok, rows
