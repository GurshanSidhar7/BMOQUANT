# Interactive pipeline walkthrough

A single-page, responsive presentation of Research Data Engine for a technical or managerial audience. Built with HTML, CSS, JavaScript modules, and SVG; no JavaScript runtime dependencies or backend web server are required.

## Run locally

From the repository root, with Node.js 18+ and Python available:

```bash
node frontend/build.mjs
python3 -m http.server 4173 --bind 127.0.0.1 --directory frontend/dist
```

Open **http://127.0.0.1:4173**. Serve over HTTP; opening `index.html` with `file://` will not load its module/data requests reliably. The included evidence is ready to use, so Python dependencies need not be installed just to view the page.

## What runs where

| Interaction | Execution |
|---|---|
| Record filters, provenance dialogs, navigation | Browser-local views of exported records |
| Editable two-price return example | Browser-local mathematical illustration |
| Price/return/volatility charts | Actual Polars outputs exported by Python; chart selection does not recalculate history |
| Quarantine/reject policy preview | Precomputed validation outcomes; does not publish a new dataset |
| Warning-threshold comparisons | Counts calculated by Python on the complete retained dataset |
| Publication replay and failure toggle | Labelled conceptual illustration; does not change files |
| SQL tabs | Recorded results from the real `QueryEngine` and SQL example files |
| Benchmark scale/time/RSS controls | Original measured JSON reports; no new benchmark is run by the browser |
| Print and downloads | Browser print/PDF, selected plotted CSV, and recorded evidence files |

There is no CSV upload, live pipeline execution, arbitrary browser SQL engine, or direct backend control in this presentation. Its goal is comprehension and traceability. Core financial/validation logic remains in Python rather than being reimplemented as a second processing pipeline.

## Refresh the evidence

After installing the Python dependencies, run from the repository root:

```bash
uv run pytest --junitxml=/tmp/research-data-walkthrough-pytest.xml
uv run python scripts/export_walkthrough.py \
  --test-report /tmp/research-data-walkthrough-pytest.xml
node frontend/build.mjs
```

The exporter creates a fresh deterministic synthetic dataset in a temporary directory, runs the actual pipeline, reads its Parquet outputs, queries DuckDB, and exports selected rows plus three securities' full histories. Original datasets are untouched. It embeds the current backend Git commit and actual source function snippets, preserves exact numerical outputs, labels non-finite raw values as strings, and replaces machine-specific data paths with portable display paths.

`assets/evidence.json` contains the primary payload. `pipeline-report.json`, a 40-record raw sample, the original 100k/1M benchmark reports, and SHA-256 checksums are downloadable. The sample CSV is an excerpt; the processing report's input hash identifies the full generated input, not that excerpt. A supplied failing/empty JUnit test report prevents certification/export. The Python test count excludes the browser and JavaScript tests, which are reported separately.

Refreshing evidence produces new timestamps and snapshot IDs. Financial values and row decisions reproduce under the locked environment. Benchmarks are copied byte-for-byte from the repository; refresh them separately only when intentionally rerunning measurements.

## Verify the frontend

```bash
node --test frontend/tests/model.test.mjs
```

These tests cover filtering/duplicate retention, preserved historical context, the illustrative return calculator against an actual price pair, chart null handling, measured benchmark pairing, and CSV escaping.

Optional full browser check, after starting the local HTTP server:

```bash
cd frontend
npm install --no-save playwright
npx playwright install chromium
node tests/browser.mjs
```

`WALKTHROUGH_URL` selects a different server, `CHROME_EXECUTABLE` uses an installed Chrome executable, and `WALKTHROUGH_SCREENSHOTS` chooses a screenshot/PDF directory (default `/tmp/research-data-walkthrough-qa`). `PLAYWRIGHT_MODULE` can point to a temporary Playwright installation. The browser test checks actual interactions, all three SQL views, benchmark changes, downloads, keyboard inspection, print rendering, and mobile overflow, and fails on browser errors.

The page respects reduced-motion preferences, supports keyboard focus, uses a native accessible record dialog, and includes text tables for chart inspection. Its hosted Sites identity is in `.openai/hosting.json`; no credentials belong in this directory.

## Publication

The configured Sites address is [research-data-engine-walkthrough.gurshansidhar7.chatgpt.site](https://research-data-engine-walkthrough.gurshansidhar7.chatgpt.site), with owner-private access. Show it while signed in or use the local preview during a meeting. Sharing with other viewers is a separate access setting; a URL alone does not grant them access. The repository retains all frontend source and portable evidence independently of hosting.
