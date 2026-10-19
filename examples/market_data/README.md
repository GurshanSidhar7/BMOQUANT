# Frozen real historical samples

Three intentionally small snapshots cover **2025-02-24 through 2025-12-31**. They are real historical observations, separate from the generated ten-stock validation fixture. They are not live prices.

| Instrument | Provider | Observations | Contract / unit |
|---|---|---:|---|
| NVIDIA (`NVDA`) | [Yahoo Finance](https://finance.yahoo.com/quote/NVDA/history/) | 216 | Provider OHLCV; USD per share; volume in shares |
| SanDisk (`SNDK`) | [Yahoo Finance](https://finance.yahoo.com/quote/SNDK/history/) | 216 | Provider OHLCV; USD per share; volume in shares |
| WTI Cushing spot (`WTI`) | [U.S. Energy Information Administration](https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=RWTC&f=D) | 214 | Published daily spot assessment; USD per barrel; no OHLC or volume |

SanDisk's present independent company started regular-way Nasdaq trading on February 24, 2025. The sample avoids merging its old ticker history with the current listing. See [Sandisk's listing announcement](https://www.nasdaq.com/press-release/sandisk-celebrates-nasdaq-listing-after-completing-separation-western-digital-2025-02).

Equity CSVs preserve provider OHLCV as supplied, including floating-point values. The provider's adjusted-close field is not used. The project does not independently adjust for corporate actions, calculate dividends, or claim total returns. Both equity files pass the same canonical normalization, validation, and analytics pipeline used by the synthetic example. Zero rows were quarantined in this recorded sample.

WTI uses EIA's daily Monday–Friday table. Blank cells remain absent observations, never zeros or forward-filled prices. Its separate positive-price contract validates published dates, finite positive prices, and unique keys, then shares the equity price-return/volatility functions. It does not fabricate opening/high/low prices or volume to meet the equity schema. Those fields stay blank in the workspace's common CSV layout. Signed commodity prices require a different return definition and are outside this small 2025 adapter. WTI spot is not a futures contract, rolled futures index, oil stock, or ETF.

Real samples use `calendar: none`; an exchange calendar is not implemented. A return spans adjacent observed prices and can therefore span a publication or trading gap. Full trailing windows and 252-observation annualization match the existing definitions. No training errors have been injected into real observations.

`manifest.json` records each provider, source/download URL, retrieval time, first/last date, count, normalized CSV SHA-256, and downloaded-response SHA-256. Exports refuse edited or mismatched snapshots. The CSV is the canonical saved input, not a byte-for-byte copy of a provider's JSON/HTML response. All tests and site builds use the frozen snapshots without network access.

## Run or refresh

Run equities through the existing pipeline:

```bash
uv run research-data ingest --config configs/real_equities.yaml
```

Read the spot sample with its explicit contract:

```python
from pathlib import Path
from research_data_engine.market_samples import load_spot_prices

prices = load_spot_prices(Path("examples/market_data/spot/WTI.csv"))
print(prices.select("date", "close", "simple_return", "realized_vol_20"))
```

Refresh the same historical window explicitly, then rerun tests and the walkthrough export:

```bash
uv run python scripts/fetch_market_samples.py
uv run pytest --junitxml=/tmp/research-data-walkthrough-pytest.xml
uv run python scripts/export_walkthrough.py --test-report /tmp/research-data-walkthrough-pytest.xml
node frontend/build.mjs
```

Provider availability and historical revisions can change downloaded values. Keep the resulting hashes, retrieval time, and source labels. The repository's software license does not grant additional rights to third-party market data. EIA permits reuse with attribution under its [copyright and reuse policy](https://www.eia.gov/about/copyrights_reuse.php); the snapshot acknowledges EIA as its source and records the retrieval date. Provider data retains its applicable terms.
