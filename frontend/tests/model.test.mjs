import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  filterRecords,
  selectHistory,
  returnExample,
  chartGeometry,
  benchmarkPairs,
  csvText,
} from '../model.mjs';

const evidence = JSON.parse(
  readFileSync(new URL('../assets/evidence.json', import.meta.url), 'utf8'),
);

test('record filters preserve all duplicate members and retain warnings separately', () => {
  const quarantine = filterRecords(evidence.records, 'quarantined');
  assert.equal(quarantine.length, evidence.report.quarantined_row_count);
  assert.equal(quarantine.filter((record) => record.errors.includes('duplicate_key')).length, 2);
  assert.ok(
    filterRecords(evidence.records, 'warning').every((record) => record.errors.length === 0),
  );
});

test('date slices use already computed history instead of recalculating the first return', () => {
  const all = evidence.series.SYN0001;
  const selected = selectHistory(all, '2025');
  assert.ok(selected.length > 200);
  assert.ok(selected[0].realized_vol_20 !== null);
  assert.equal(
    selected[0].simple_return,
    all.find((row) => row.date === selected[0].date).simple_return,
  );
});

test('illustrative return calculator agrees with an actual retained price pair', () => {
  const [first, second] = evidence.series.SYN0001;
  const result = returnExample(first.close, second.close);
  assert.ok(Math.abs(result.simple - second.simple_return) < 1e-12);
  assert.ok(Math.abs(result.log - second.log_return) < 1e-12);
  assert.equal(returnExample(0, 100), null);
  assert.equal(returnExample(NaN, 100), null);
});

test('charts preserve null gaps and empty histories without fabricating values', () => {
  const result = chartGeometry([{ close: 1 }, { close: null }, { close: 3 }], 'close');
  assert.equal(result.path.split('M').length - 1, 2);
  assert.equal(result.points.length, 2);
  assert.equal(chartGeometry([], 'close').points.length, 0);
});

test('benchmark pairing includes the true pandas baseline and measured candidates', () => {
  for (const report of Object.values(evidence.benchmarks)) {
    const pairs = benchmarkPairs(report);
    assert.equal(pairs.length, 5);
    for (const { baseline, candidate } of pairs) {
      assert.equal(baseline.engine, 'pandas');
      assert.ok(
        Math.abs(
          baseline.median_wall_seconds / candidate.median_wall_seconds -
            candidate.speedup_vs_pandas,
        ) < 1e-9,
      );
    }
  }
});

test('downloaded CSV preserves embedded commas, quotes, newlines, and nulls', () => {
  assert.equal(
    csvText([{ label: 'a,"b"\nc', value: null }], ['label', 'value']),
    'label,value\n"a,""b""\nc",\n',
  );
});
