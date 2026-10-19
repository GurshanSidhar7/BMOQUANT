"""Refresh the three small historical samples; never called by build or tests."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from research_data_engine.market_samples import (
    EIA_URL,
    END,
    START,
    load_spot_prices,
    parse_eia_spot,
    parse_yahoo_prices,
    yahoo_url,
)

ROOT = Path(__file__).resolve().parents[1]


def fetch_samples(output: Path, responses: Path | None = None) -> dict:
    samples = []
    for symbol, name, kind in (
        ("NVDA", "NVIDIA", "equity"),
        ("SNDK", "SanDisk", "equity"),
        ("WTI", "WTI crude oil · Cushing spot", "commodity_spot"),
    ):
        url = EIA_URL if symbol == "WTI" else yahoo_url(symbol)
        if responses:
            body = (responses / f"{symbol}.raw").read_bytes()
        else:
            with urlopen(
                Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=45
            ) as response:
                body = response.read()
        frame = parse_eia_spot(body) if symbol == "WTI" else parse_yahoo_prices(body, symbol)
        relative = f"{'spot' if symbol == 'WTI' else 'equities'}/{symbol}.csv"
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        frame.write_csv(destination)
        if symbol == "WTI":
            load_spot_prices(destination)
        samples.append(
            {
                "symbol": symbol,
                "name": name,
                "instrument_type": kind,
                "data_kind": "real",
                "source": frame["source"][0],
                "provider": "U.S. Energy Information Administration"
                if symbol == "WTI"
                else "Yahoo Finance",
                "source_url": EIA_URL
                if symbol == "WTI"
                else f"https://finance.yahoo.com/quote/{symbol}/history/",
                "download_url": url,
                "path": relative,
                "start": frame["date"].min().isoformat(),
                "end": frame["date"].max().isoformat(),
                "rows": frame.height,
                "currency": "USD",
                "unit": "USD per barrel" if symbol == "WTI" else "USD per share",
                "has_volume": symbol != "WTI",
                "price_basis": "Daily Cushing spot assessment; no OHLC or trading volume supplied."
                if symbol == "WTI"
                else (
                    "Provider OHLC as supplied. Adjusted-close field is not used; "
                    "no additional corporate-action adjustment. Price returns, not total returns."
                ),
                "retrieved_at": datetime.now(UTC).isoformat(),
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "provider_response_sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    manifest = {
        "requested_start": START.isoformat(),
        "requested_end": END.isoformat(),
        "mode": "Frozen historical samples, not a live feed",
        "samples": samples,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "examples" / "market_data")
    parser.add_argument("--responses", type=Path, help="Use already downloaded provider responses")
    args = parser.parse_args()
    result = fetch_samples(args.output, args.responses)
    for sample in result["samples"]:
        print(
            f"{sample['symbol']}: {sample['rows']} real observations, "
            f"{sample['start']}–{sample['end']}"
        )


if __name__ == "__main__":
    main()
