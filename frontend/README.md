# Research Data Engine frontend

Two responsive pages with no JavaScript runtime dependencies:

- **How it works** (`index.html`): one page explaining the five steps, with definitions, examples, actual row accounting, and optional calculation details.
- **Research workspace** (`workspace.html`): a practical stock-history review. Choose NVIDIA, SanDisk, WTI Cushing spot, or one of 10 synthetic test stocks, apply a date range, inspect recorded measures and quality flags, and export every retained row in the selection.

## Run locally

From the repository root with Node.js 18+ and Python available:

```bash
node frontend/build.mjs
python3 -m http.server 4173 --bind 127.0.0.1 --directory frontend/dist
```

Open **http://127.0.0.1:4173/** or **http://127.0.0.1:4173/workspace.html**. Serve over HTTP so module and JSON requests work. Included evidence is ready to use without installing the Python project's dependencies.

## What runs where

Python runs the real pipeline in a temporary directory and exports the saved Parquet values. The browser loads one stock history at a time, filters it, displays charts/tables, and generates the CSV. No financial returns or rolling volatility are recalculated after the date filter. There is no CSV upload, live market connection, browser SQL runtime, or new ingestion job.

The walkthrough calculator is an explicitly separate illustration. Workspace summaries calculate first-to-last selected price change and mean selected volume; these differ from previous-observation returns and trailing 20-observation volume. Volatility is the latest selected row's stored 20-return value. Empty windows show no results; missing history stays blank. Changed selection controls disable download until applied, so the download matches the displayed applied selection.

The table is paginated; the download contains **all** selected rows with OHLCV, source, price return, volatility, source-row references, and warning codes. The quality panel follows the selected source dataset. The synthetic fixture has seven deliberate quarantined records; the two real equity files and the WTI spot sample have their own reports. WTI volume and OHLC are unavailable and remain blank; its unit is USD per barrel. The CSV identifies data kind, instrument type, and price unit. A row can have multiple errors or warning flags.

## Refresh evidence

With the Python environment installed, from the repository root:

```bash
uv run pytest --junitxml=/tmp/research-data-walkthrough-pytest.xml
uv run python scripts/export_walkthrough.py --test-report /tmp/research-data-walkthrough-pytest.xml
node --test frontend/tests/model.test.mjs
node frontend/build.mjs
```

The exporter generates a disposable ten-stock synthetic file, validates the frozen real samples from `examples/market_data/`, uses the real ingestion and DuckDB APIs, records source-function excerpts, copies original benchmark evidence, and writes strict portable JSON. `assets/history/` contains one compact JSON file per stock/source. Their row counts reconcile with the combined workspace total; `assets/checksums.json` covers the assets recursively. No private input dataset is uploaded. Test certification reflects the supplied local JUnit run, not hosted CI.

## Verification

```bash
node --test frontend/tests/model.test.mjs
```

Optional browser checks use Playwright and an existing Chrome/Chromium. Start the preview, then run `node frontend/tests/browser.mjs`; set `PLAYWRIGHT_MODULE` and `CHROME_EXECUTABLE` when those are installed outside this folder. Checks cover both pages, the 13-instrument selector and all three real samples, date errors/empty results, retained calculation history, CSV contents, pagination, warnings, duplicate quarantine, keyboard chart inspection, mobile width, and PDF output. Artifacts default to `/tmp/research-data-walkthrough-qa`; `preview/` is an ignored convenience location for IDE review.

## Hosting

Production URLs: [How it works](https://bmoquant.vercel.app/) and [Research workspace](https://bmoquant.vercel.app/workspace.html). The project uses Vercel Authentication for all deployments, including production, to retain private access. The connected GitHub repository uses `main` as its production branch.

Vercel builds this frontend from the repository root using the tracked `vercel.json`: framework **Other**, build command `node frontend/build.mjs`, output directory `frontend/dist`, and no dependency installation. The Python engine is not deployed as a web service.

After signing into Vercel and linking the project, publish from the repository root:

```bash
npx --yes vercel@latest deploy --prod
```

`.vercelignore` limits the upload to the frontend source and labelled synthetic/real historical evidence. It excludes local previews, dependencies, generated output, and the previous Sites configuration. `.vercel/` contains checkout-local project settings and is ignored by Git. Preserve the project's configured deployment protection when publishing updates.

The earlier `.openai/hosting.json` identity is retained for the original Sites publication; Vercel does not use it.

The Python CLI/API remains the way to prepare other files. This frontend is a transparent walkthrough and a working research view over the bundled output.
