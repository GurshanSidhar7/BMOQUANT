"""Internal subprocess entry point, keeping benchmark imports outside timed calls."""

import argparse
import json
from pathlib import Path

from research_data_engine.benchmarking import WORKLOADS, measure_workload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["pandas", "polars", "duckdb"], required=True)
    parser.add_argument("--workload", choices=list(WORKLOADS), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            measure_workload(
                engine=args.engine,
                workload=args.workload,
                directory=args.directory,
                repetitions=args.repetitions,
            ),
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
