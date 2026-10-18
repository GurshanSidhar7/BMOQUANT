import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  filterRecords,
  selectHistory,
  returnExample,
  chartGeometry,
  benchmarkPairs,
  csvText,
} from "../model.mjs";

const evidence = JSON.parse(
  readFileSync(new URL("../assets/evidence.json", import.meta.url), "utf8"),
);

test("record filters preserve all duplicate members and retain warnings separately", () => {
  const quarantine = filterRecords(evidence.records, "quarantined");
  assert.equal(quarantine.length, evidence.report.quarantined_row_count);
  assert.equal(
    quarantine.filter((record) => record.errors.includes("duplicate_key"))
      .length,
    2,
  );
  assert.ok(
    filterRecords(evidence.records, "warning").every(
      (record) => record.errors.length === 0,
    ),
  );
});

test("date slices use already computed history instead of recalculating the first return", () => {
  const all = evidence.series.SYN0001;
  const selected = selectHistory(all, "2025");
  assert.ok(selected.length > 200);
  assert.ok(selected[0].realized_vol_20 !== null);
  assert.equal(
    selected[0].simple_return,
    all.find((row) => row.date === selected[0].date).simple_return,
  );
});

test("illustrative return calculator agrees with an actual retained price pair", () => {
  const [first, second] = evidence.series.SYN0001;
  const result = returnExample(first.close, second.close);
  assert.ok(Math.abs(result.simple - second.simple_return) < 1e-12);
  assert.ok(Math.abs(result.log - second.log_return) < 1e-12);
  assert.equal(returnExample(0, 100), null);
  assert.equal(returnExample(NaN, 100), null);
});

test("charts preserve null gaps and empty histories without fabricating values", () => {
  const result = chartGeometry(
    [{ close: 1 }, { close: null }, { close: 3 }],
    "close",
  );
  assert.equal(result.path.split("M").length - 1, 2);
  assert.equal(result.points.length, 2);
  assert.equal(chartGeometry([], "close").points.length, 0);
});

test("benchmark pairing includes the true pandas baseline and measured candidates", () => {
  for (const report of Object.values(evidence.benchmarks)) {
    const pairs = benchmarkPairs(report);
    assert.equal(pairs.length, 5);
    for (const { baseline, candidate } of pairs) {
      assert.equal(baseline.engine, "pandas");
      assert.ok(
        Math.abs(
          baseline.median_wall_seconds / candidate.median_wall_seconds -
            candidate.speedup_vs_pandas,
        ) < 1e-9,
      );
    }
  }
});

test("downloaded CSV preserves embedded commas, quotes, newlines, and nulls", () => {
  assert.equal(
    csvText([{ label: 'a,"b"\nc', value: null }], ["label", "value"]),
    'label,value\n"a,""b""\nc",\n',
  );
});

test("research date filters preserve boundaries, earlier calculations, and honest empty results", async () => {
  const { dateRangeError, researchSlice } = await import("../model.mjs");
  const all = evidence.series.SYN0001;
  const rows = researchSlice(all, "2025-01-01", "2025-12-31");
  assert.equal(rows.length, 261);
  assert.ok(rows[0].realized_vol_20 > 0);
  assert.strictEqual(
    rows[0],
    all.find((row) => row.date === "2025-01-01"),
  );
  assert.equal(researchSlice(all, "2030-01-01", "2030-12-31").length, 0);
  assert.ok(dateRangeError("2025-12-31", "2025-01-01"));
  assert.ok(dateRangeError("2025-02-29", "2025-03-01"));
  assert.equal(dateRangeError("2024-02-29", "2024-02-29"), null);
  assert.throws(() => researchSlice(all, "", "2025-01-01"), RangeError);
});

test("research summaries distinguish selected price change from the previous-observation return", async () => {
  const { summarizeSlice, RESEARCH_COLUMNS } = await import("../model.mjs");
  const rows = [
    {
      date: "2025-01-02",
      close: 100,
      volume: 1000,
      simple_return: 0.1,
      realized_vol_20: null,
      _warnings: [],
    },
    {
      date: "2025-01-03",
      close: 110,
      volume: 3000,
      simple_return: 0.1,
      realized_vol_20: 0.25,
      _warnings: ["volume_change"],
    },
  ];
  const summary = summarizeSlice(rows);
  assert.ok(Math.abs(summary.priceChange - 0.1) < 1e-12);
  assert.equal(summary.meanVolume, 2000);
  assert.equal(summary.latestVolatility, 0.25);
  assert.equal(summary.warningRows, 1);
  assert.equal(summarizeSlice(rows.slice(0, 1)).priceChange, 0);
  assert.equal(summarizeSlice(rows.slice(0, 1)).latestVolatility, null);
  assert.equal(summarizeSlice([]), null);
  assert.ok(RESEARCH_COLUMNS.includes("_source_row"));
  assert.ok(RESEARCH_COLUMNS.includes("_warnings"));
});
