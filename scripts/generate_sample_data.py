"""Generate deterministic SYNTHETIC prices without API keys or network access."""

import argparse
from pathlib import Path

from research_data_engine.sample_data import write_sample_csv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/raw/synthetic_prices.csv"))
    parser.add_argument("--symbols", type=int, default=50)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dirty", action="store_true", help="Inject known errors and warnings")
    args = parser.parse_args()
    path = write_sample_csv(
        args.output, dirty=args.dirty, symbols=args.symbols, rows=args.rows, seed=args.seed
    )
    print(f"SYNTHETIC weekday-calendar CSV written to {path}")


if __name__ == "__main__":
    main()
