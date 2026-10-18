export const METRICS = {
  close: { label: 'Close price', type: 'price', description: 'Unadjusted synthetic closing price' },
  simple_return: {
    label: 'Simple price return',
    type: 'percent',
    description: 'Relative to the previous retained observation',
  },
  realized_vol_20: {
    label: '20-return realized volatility',
    type: 'percent',
    description: 'Annualized · sample standard deviation · full window',
  },
  realized_vol_30: {
    label: '30-return realized volatility',
    type: 'percent',
    description: 'Annualized · sample standard deviation · full window',
  },
  average_volume_20: {
    label: '20-observation average volume',
    type: 'volume',
    description: 'Trailing observed volumes · full window',
  },
  dollar_volume: {
    label: 'Approximate dollar volume',
    type: 'dollars',
    description: 'Close × volume · price currency',
  },
};

export const ERROR_LABELS = {
  duplicate_key: 'Duplicate observation key',
  invalid_ohlc: 'Inconsistent OHLC relationships',
  invalid_price: 'Nonpositive price',
  malformed_value: 'Unparseable nonempty value',
  missing_value: 'Required value is missing',
  negative_volume: 'Negative trading volume',
  nonfinite_price: 'Non-finite price',
  nonfinite_return: 'Non-finite return',
  nonfinite_analytics: 'Non-finite derived value',
};

export const WARNING_LABELS = {
  extreme_return: 'Large price return; retained',
  volume_change: 'Large volume change; retained',
  stale_price: 'Consecutive unchanged closes; retained',
  missing_expected_sessions: 'Approximate weekday gap; retained',
};

export function filterRecords(records, filter) {
  if (filter === 'all') return records;
  return records.filter((record) => record.status === filter);
}

export function selectHistory(rows, range) {
  if (range === 'first60') return rows.slice(0, 60);
  if (range === '2025')
    return rows.filter((row) => row.date >= '2025-01-01' && row.date <= '2025-12-31');
  return rows;
}

export function returnExample(previous, current) {
  if (![previous, current].every((value) => Number.isFinite(value) && value > 0)) return null;
  const simple = current / previous - 1;
  const log = Math.log(current) - Math.log(previous);
  if (![simple, log].every(Number.isFinite)) return null;
  return { simple, log };
}

export function chartGeometry(rows, metric, width = 900, height = 290) {
  const bounds = { left: 66, right: width - 25, top: 25, bottom: height - 38 };
  const valid = rows
    .map((row, index) => ({ row, index, value: row[metric] }))
    .filter((point) => typeof point.value === 'number' && Number.isFinite(point.value));
  if (!valid.length) return { path: '', points: [], bounds, min: 0, max: 1 };
  let min = Math.min(...valid.map((point) => point.value));
  let max = Math.max(...valid.map((point) => point.value));
  const padding = (max - min || Math.abs(max) || 1) * 0.12;
  min -= padding;
  max += padding;
  const pointMap = new Map(valid.map((point) => [point.index, point]));
  const points = valid.map((point) => ({
    ...point,
    x: bounds.left + (point.index / Math.max(1, rows.length - 1)) * (bounds.right - bounds.left),
    y: bounds.bottom - ((point.value - min) / (max - min)) * (bounds.bottom - bounds.top),
  }));
  const coordinateMap = new Map(points.map((point) => [point.index, point]));
  let path = '';
  let connected = false;
  for (let index = 0; index < rows.length; index++) {
    if (!pointMap.has(index)) {
      connected = false;
      continue;
    }
    const point = coordinateMap.get(index);
    path += `${connected ? 'L' : 'M'}${point.x.toFixed(2)},${point.y.toFixed(2)} `;
    connected = true;
  }
  return { path: path.trim(), points, bounds, min, max };
}

export function benchmarkPairs(report) {
  const workloads = [...new Set(report.measurements.map((record) => record.workload))];
  return workloads.map((workload) => {
    const baseline = report.measurements.find(
      (record) => record.workload === workload && record.engine === 'pandas',
    );
    const candidate = report.measurements.find(
      (record) => record.workload === workload && record.engine !== 'pandas',
    );
    if (!baseline || !candidate) throw new Error(`Missing paired measurements for ${workload}`);
    return { workload, baseline, candidate };
  });
}

export function csvText(rows, columns) {
  const escape = (value) => {
    const text =
      value === null || value === undefined
        ? ''
        : typeof value === 'object'
          ? JSON.stringify(value)
          : String(value);
    return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  return (
    [columns, ...rows.map((row) => columns.map((column) => row[column]))]
      .map((values) => values.map(escape).join(','))
      .join('\n') + '\n'
  );
}
