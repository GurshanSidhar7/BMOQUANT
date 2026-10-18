import json

import polars as pl
import pytest

from research_data_engine.benchmarking import run_benchmarks, verify_equivalence
from research_data_engine.exceptions import BenchmarkError


def test_correctness_gate_blocks_incorrect_results():
    with pytest.raises(BenchmarkError, match="Correctness gate failed"):
        verify_equivalence(
            pl.DataFrame({"value": [1.0]}), pl.DataFrame({"value": [1.2]}), workload="fixture"
        )


def test_all_benchmark_workloads_measure_and_write_reports(tmp_path):
    report = run_benchmarks(rows=200, repetitions=2, output=tmp_path)
    saved = json.loads((tmp_path / "measured-200.json").read_text())
    assert len(saved["measurements"]) == 10
    assert len(saved["input_sha256"]) == 2
    for record in saved["measurements"]:
        assert len(record["samples"]) == 2
        assert record["median_wall_seconds"] > 0
        assert record["median_sampled_peak_rss_bytes"] > 0
        assert record["speedup_vs_pandas"] > 0
    assert "SYNTHETIC" in report["markdown"]
    assert (tmp_path / "measured-200.md").is_file()
