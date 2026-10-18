# Explaining Research Data Engine

This is an independent portfolio project by Gurshan Sidhar. The bundled prices are synthetic. Describe the work you understand and can demonstrate; BMO did not commission or endorse it.

## Start with the problem

“I wanted to reduce the repeated cleaning that happens before a stock-price analysis. This project reads price CSVs, checks their records, calculates a few standard measures, and saves a clean file that another script can use. It also keeps a separate file of unusable records with the reasons. I used synthetic data to make the example repeatable.”

That is the central project. Performance measurements and publication safeguards support it; they do not need to lead the explanation.

## The five steps, in plain language

### 1. Read the file

A CSV is a plain-text spreadsheet. Each row describes a stock on a date: opening price, highest price, lowest price, closing price, and volume (shares traded). A source label identifies the feed.

The project remembers the file and source-record number. If something goes wrong, the researcher can find the original record.

Implementation: `ingestion.py` discovers files in a predictable order. Polars reads fields as text first so mixed values do not silently change a column's type.

### 2. Make the fields consistent

A small YAML configuration maps incoming names such as `ticker` to the standard `symbol` column. It defines the date format. The code trims and uppercases symbols, converts dates to dates, prices to decimal numbers, and volume to whole numbers.

Text such as `not-a-date` is marked as a parsing error. It is not silently treated as a valid date or corrected by guessing.

Implementation: `config.py` checks settings; `transformations.py` applies the mappings and conversions.

### 3. Check the records

An **error** means the record violates the rules: missing required values, a broken date, a nonpositive price, negative volume, impossible high/low relationships, or a duplicate stock/date/source. Both members of a duplicate pair are set aside because there is no rule for choosing the better copy.

A **warning** means a record deserves review: a large price move, a large volume change, repeated unchanged prices, or an approximate weekday gap. Warnings stay in the clean data because unusual does not necessarily mean wrong.

**Quarantine** means saving offending rows separately with reasons. Configuration can instead reject the whole run. Missing required values reject by default; the demonstration explicitly uses quarantine so all example errors can be inspected.

The demo contains **65,201 input rows = 65,194 retained rows + 7 quarantined rows**. Some rows fail more than one check, so reason counts can exceed seven.

Implementation: `validation.py`. It checks the input, calculates analytics once on retained rows, and adds warnings. If the arithmetic exceeds the supported numeric range, it stops for input review. It does not repeatedly remove observations to repair a calculation.

### 4. Calculate a few useful measures

The retained rows are sorted by stock, source, and date. Each source stays separate.

- **Price return:** current close ÷ previous retained close − 1. A move from 100 to 102 is a 2% return. If a date is missing, this return spans that gap.
- **Recent volatility:** variation in the last 20 log returns. It describes recent price swings. It needs 21 retained prices, and stays blank until enough history exists.
- **Average volume:** mean shares traded over the last 20 retained observations. It is a simple activity measure.

The precise volatility definition is sample standard deviation (`ddof=1`) of 20 trailing log returns × √252. Log return is ln(current close) − ln(previous close). The library also provides a 30-return window and close × volume as an approximate dollar-volume measure.

These are unadjusted price measures. Splits and dividends are not handled. None is a prediction, trading strategy, or proof of investment value.

Implementation: `analytics.py`. Calculations use current and earlier observations. Date selections read the stored results, preserving pre-start history.

### 5. Save the result and use it

The project saves the retained data as **Parquet**, a compact file format that remembers dates and number types. It also saves quarantined records and a JSON report of counts, settings, and input fingerprints.

A complete new version becomes current only after its files are written. Reruns replace the active dataset rather than appending the same observations. If publication fails, the old version remains available. This is a local single-writer approach.

**DuckDB** lets a researcher ask SQL questions directly against the saved Parquet. The Python API exposes the same stored data as Polars frames.

Implementation: `pipeline.py` joins the steps; `storage.py` saves versions; `queries.py` reads them.

## The two-page demonstration

Build and serve the frontend from the repository root:

```bash
node frontend/build.mjs
python3 -m http.server 4173 --bind 127.0.0.1 --directory frontend/dist
```

1. Open `http://127.0.0.1:4173/`. The **How it works** page explains the five steps on one page. Show the seven set-aside records in the row accounting and try the two-price return example.
2. Open **Research workspace**. The task is: “I need a clean stock-price history for a research notebook.” Select a stock and dates, apply the selection, and review the summary and chart.
3. Switch to recent volatility. Explain that the first displayed date can have a value because Python calculated it with earlier history before the date filter.
4. Download the selected CSV. It includes every retained row in the selection, not only the table's current page.
5. Select `SYN0000`, January–February 2021, to review warning flags. Inspect both duplicate records in the quarantine table (source rows 12 and 65,202).

Be precise about execution: Python prepared these outputs offline. The website filters and exports them locally in the browser. It does not run a new ingestion job, accept uploads, or connect to live markets. All 50 synthetic stocks have downloadable histories.

The workspace's **price change** compares its first and last selected closes; it differs from a row's return against the previous retained observation. Its **average daily volume** averages the selected observations; it differs from the library's trailing 20-observation average. Its **recent volatility** is the stored 20-return value on the latest selected row.

## Questions worth being ready for

**Why is this valuable?** It makes routine preparation consistent and inspectable. Another notebook can start from a clean file instead of rewriting the same checks.

**Why Polars?** Its column operations suit parsing, checking, sorting, and calculations. This project uses an in-memory validation boundary; lazy scanning does not make every operation memory-free.

**Why DuckDB too?** Some researchers prefer SQL. DuckDB reads local Parquet directly without running a database server. Polars handles preparation; DuckDB is an optional way to use the result.

**Why keep unusual moves?** A large move may reflect a real event, a split, or an error. A simple rule cannot distinguish those causes. Keep it flagged for review.

**Why not choose one duplicate?** There is no implemented source-quality rule for deciding which copy is right. Setting aside both makes the ambiguity visible.

**How did you check the maths?** Tests compare returns and rolling volatility against independent NumPy references, check short histories and source boundaries, and verify that adding future rows does not change earlier results.

**What is the main limitation?** These are synthetic, unadjusted prices. Real research would first need suitable licensed inputs, stable identifiers, corporate-action handling, and exchange calendars. The current gap check only knows weekdays.

**What about the speed claims?** A separate exercise measured matched 100k and 1M synthetic workloads after checking complete result agreement. Results vary by workload and machine; faster wall time did not always mean lower memory. Show `benchmarks/results/` if asked. The 5M case was not executed. These measurements do not establish end-to-end production throughput.

**What would you do next?** Take a representative real file and review its data contract, adjustments, and calendar before adding more indicators or infrastructure.

## Optional terminal demonstration

```bash
uv run pytest
uv run research-data demo --directory /tmp/research-data-demo
uv run research-data query --dataset /tmp/research-data-demo/processed/equity_prices --sql examples/security_summary.sql --limit 5
```

Expected: the recorded row accounting, saved report/quarantine locations, and a query result from the saved synthetic dataset. Tests, examples, and benchmark methodology are in the repository for deeper discussion.
