import {
  METRICS,
  ERROR_LABELS,
  WARNING_LABELS,
  filterRecords,
  selectHistory,
  returnExample,
  chartGeometry,
  benchmarkPairs,
  csvText,
} from './model.mjs';

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const integer = new Intl.NumberFormat('en-CA', { maximumFractionDigits: 0 });
const dateLabel = (value) =>
  new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`));
const number = (value, digits = 2) =>
  new Intl.NumberFormat('en-CA', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
const escapeHTML = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character],
  );
const statusName = (status) =>
  ({ valid: 'Valid', quarantined: 'Quarantined', warning: 'Warning · retained' })[status] ?? status;
const badge = (status) =>
  `<span class="status-badge status-${status}">${statusName(status)}</span>`;
let evidence;
const state = {
  recordFilter: 'all',
  metric: 'close',
  symbol: 'SYN0000',
  range: 'first60',
  scale: '1000000',
  benchmarkMetric: 'wall',
  query: 'security_summary',
  publication: 0,
  chart: null,
  history: [],
  hoverIndex: -1,
};

function metricValue(value, metric, compact = false) {
  if (value === null || value === undefined || typeof value !== 'number' || !Number.isFinite(value))
    return '—';
  const type = METRICS[metric]?.type;
  if (type === 'percent') return `${number(value * 100, compact ? 1 : 2)}%`;
  if (compact && Math.abs(value) >= 1e6)
    return `${type === 'dollars' ? '$' : ''}${number(value / 1e6, 1)}m`;
  if (compact && Math.abs(value) >= 1e3)
    return `${type === 'dollars' ? '$' : ''}${number(value / 1e3, 0)}k`;
  if (type === 'price' || type === 'dollars') return `$${number(value, 2)}`;
  return integer.format(value);
}

function plainValue(value, column) {
  if (value === null || value === undefined) return '—';
  if (typeof value !== 'number') return String(value);
  if (/return|volatility|realized_vol/.test(column)) return `${number(value * 100, 3)}%`;
  if (/volume|observations/.test(column)) return integer.format(value);
  return number(value, 3);
}

function pressed(selector, attribute, selected) {
  $$(selector).forEach((button) => {
    const active = button.getAttribute(attribute) === String(selected);
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
}

function renderInput() {
  const columns = ['ticker', 'trade_date', 'open', 'high', 'low', 'close', 'volume', 'source'];
  $('#input-head').innerHTML = `<tr>${columns.map((column) => `<th>${column}</th>`).join('')}</tr>`;
  $('#input-body').innerHTML = evidence.records
    .slice(0, 6)
    .map(
      (record) =>
        `<tr>${columns
          .map((column) => {
            const value = record.raw[column];
            const error =
              value === null ||
              (column === 'trade_date' && record.parse_errors.includes('date')) ||
              (column === 'volume' && Number(value) < 0) ||
              (column === 'close' && (Number(value) <= 0 || !Number.isFinite(Number(value))));
            return `<td${error ? ' class="bad-cell"' : ''} title="${escapeHTML(value ?? 'Missing value')}">${escapeHTML(value ?? 'null')}</td>`;
          })
          .join('')}</tr>`,
    )
    .join('');
  const mapping = {
    symbol: ['ticker', 'String'],
    date: ['trade_date', 'Date'],
    open: ['open', 'Float64'],
    high: ['high', 'Float64'],
    low: ['low', 'Float64'],
    close: ['close', 'Float64'],
    volume: ['volume', 'Int64'],
    source: ['source', 'String'],
  };
  $('#mapping-rows').innerHTML = Object.entries(mapping)
    .map(
      ([canonical, [incoming, type]]) =>
        `<div class="mapping-row"><span>${incoming}</span><span aria-hidden="true">→</span><span>${canonical}</span><span>${type}</span></div>`,
    )
    .join('');
  $('#yaml-code').textContent = evidence.config_yaml;
}

function renderRules() {
  $('#rule-list').innerHTML = Object.entries(evidence.report.errors_by_category)
    .map(
      ([key, count], index) =>
        `<div class="rule-row"><span><span class="rule-index">${String(index + 1).padStart(2, '0')}</span>${escapeHTML(ERROR_LABELS[key] ?? key)}</span><strong class="rule-count">${count}</strong></div>`,
    )
    .join('');
}

function renderPolicy(mode) {
  pressed('[data-policy]', 'data-policy', mode);
  const valid = integer.format(evidence.report.valid_row_count);
  const quarantined = integer.format(evidence.report.quarantined_row_count);
  $('#policy-result').innerHTML =
    mode === 'reject'
      ? `<div class="mode-reject"><strong>0 new rows published</strong><p>${valid} eligible observations are held with the rejected run. The previous active snapshot stays in place.</p></div>`
      : `<strong>${valid} rows published</strong><p>${quarantined} offending records are retained in quarantine with their raw fields and reasons. The remaining observations continue.</p>`;
}

function renderRecords() {
  const selected = filterRecords(evidence.records, state.recordFilter);
  $('#record-count').textContent = `${selected.length} shown`;
  pressed('[data-record-filter]', 'data-record-filter', state.recordFilter);
  $('#record-body').innerHTML = selected
    .map(
      (record) =>
        `<tr><td>${integer.format(record.row)}</td><td>${escapeHTML(record.canonical.symbol ?? '—')}</td><td>${escapeHTML(record.canonical.date ?? record.raw.trade_date ?? '—')}</td><td class="numeric">${escapeHTML(typeof record.canonical.close === 'number' ? number(record.canonical.close) : (record.canonical.close ?? '—'))}</td><td>${badge(record.status)}</td><td><button class="inspect-button" data-inspect="${record.row}" aria-label="Inspect source row ${record.row}">↗</button></td></tr>`,
    )
    .join('');
}

function inspectRecord(row) {
  const record = evidence.records.find((item) => item.row === row);
  if (!record) return;
  $('#record-dialog-title').textContent = `Source row ${integer.format(row)}`;
  const labels = record.errors
    .map((error) => ERROR_LABELS[error] ?? error)
    .concat(record.warnings.map((warning) => WARNING_LABELS[warning] ?? warning));
  const reason =
    record.status === 'quarantined'
      ? 'Financial or structural contract violated.'
      : record.status === 'warning'
        ? 'Unusual, but retained for research.'
        : 'All required invariants passed.';
  const body = document.createElement('div');
  body.className = 'record-dialog-body';
  body.innerHTML = `<div class="record-decision">${badge(record.status)}<span>${record.file} / record ${integer.format(row)}</span></div><div class="record-reasons"><strong>${reason}</strong>${labels.length ? labels.map(escapeHTML).join('<br>') : 'The observation is eligible for trailing analytics and publication.'}</div><div class="record-comparison"><div><h3>Raw mapped input</h3><pre></pre></div><div><h3>Canonical values</h3><pre></pre></div></div>${record.parse_errors.length ? `<p class="record-parse-note">Parse failure in: ${record.parse_errors.map(escapeHTML).join(', ')}. The original nonempty text is preserved.</p>` : ''}${record.analytics ? '<div class="record-analytics"><h3>Computed analytics</h3><pre></pre></div>' : ''}`;
  const snippets = body.querySelectorAll('pre');
  snippets[0].textContent = JSON.stringify(record.raw, null, 2);
  snippets[1].textContent = JSON.stringify(record.canonical, null, 2);
  if (record.analytics) snippets[2].textContent = JSON.stringify(record.analytics, null, 2);
  if (record.errors.includes('duplicate_key')) {
    const match = evidence.records.find(
      (other) =>
        other.row !== row &&
        other.errors.includes('duplicate_key') &&
        other.canonical.symbol === record.canonical.symbol &&
        other.canonical.date === record.canonical.date &&
        other.canonical.source === record.canonical.source,
    );
    if (match) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'record-duplicate-link';
      button.textContent = `Inspect the matching duplicate at source row ${integer.format(match.row)} →`;
      button.addEventListener('click', () => inspectRecord(match.row));
      body.append(button);
    }
  }
  $('#record-dialog-content').replaceChildren(body);
  if (!$('#record-dialog').open) $('#record-dialog').showModal();
}

function updateThreshold() {
  const threshold = Number($('#warning-threshold').value);
  const result = evidence.threshold_counts.find((item) => item.threshold === threshold);
  $('#threshold-count').textContent =
    `${integer.format(result.count)} flagged · ${integer.format(evidence.report.valid_row_count)} retained`;
}

function updateCalculator() {
  const values = returnExample(
    $('#previous-price').valueAsNumber,
    $('#current-price').valueAsNumber,
  );
  $('#simple-result').textContent = values ? `${number(values.simple * 100)}%` : '—';
  $('#log-result').textContent = values ? `${number(values.log * 100)}%` : '—';
  $('#calculator-note').textContent = values
    ? 'An editable mathematical illustration. It does not change the recorded prices.'
    : 'Enter two positive, finite prices with a representable return.';
}

function renderChart() {
  const rows = selectHistory(evidence.series[state.symbol], state.range);
  const geometry = chartGeometry(rows, state.metric);
  state.chart = geometry;
  state.history = rows;
  state.hoverIndex = -1;
  $('#chart-tooltip').hidden = true;
  pressed('[data-metric]', 'data-metric', state.metric);
  $('#chart-metric-label').textContent = METRICS[state.metric].label.toUpperCase();
  $('#chart-last-value').textContent = metricValue(rows.at(-1)?.[state.metric], state.metric);
  $('#chart-caption').textContent =
    `${rows.length.toLocaleString()} retained observations · ${dateLabel(rows[0].date)} – ${dateLabel(rows.at(-1).date)}`;
  $('#chart-svg-title').textContent = `${state.symbol}: ${METRICS[state.metric].label}`;
  $('#chart-svg-description').textContent =
    `${METRICS[state.metric].description}. ${rows.length} retained observations, ${rows.filter((row) => row[state.metric] === null).length} null values. No missing observations are filled.`;
  const { bounds, min, max, path } = geometry;
  const grid = Array.from({ length: 5 }, (_, index) => {
    const y = bounds.top + (index * (bounds.bottom - bounds.top)) / 4;
    const value = max - (index * (max - min)) / 4;
    return `<line x1="${bounds.left}" x2="${bounds.right}" y1="${y}" y2="${y}" stroke="#edf0f6" stroke-width="1"/><text x="${bounds.left - 13}" y="${y + 3}" text-anchor="end" fill="#9aa8bc" font-size="9" font-family="monospace">${metricValue(value, state.metric, true)}</text>`;
  }).join('');
  const ticks = Array.from({ length: 5 }, (_, index) => {
    const position = Math.round((index * (rows.length - 1)) / 4);
    const x = bounds.left + (index * (bounds.right - bounds.left)) / 4;
    const date = rows[position].date;
    const label = state.range === 'all' ? date.slice(0, 7) : `${date.slice(5, 7)}/${date.slice(8)}`;
    return `<text x="${x}" y="${bounds.bottom + 24}" text-anchor="middle" fill="#9aa8bc" font-size="9" font-family="monospace">${label}</text>`;
  }).join('');
  const warningPoints = geometry.points
    .filter((point) => point.row._warnings.includes('extreme_return') && state.metric === 'close')
    .map(
      (point) =>
        `<circle cx="${point.x}" cy="${point.y}" r="3.5" fill="#bd9352" stroke="white" stroke-width="2"/>`,
    )
    .join('');
  const layer =
    $('#history-chart .chart-layer') ?? document.createElementNS('http://www.w3.org/2000/svg', 'g');
  layer.setAttribute('class', 'chart-layer');
  layer.innerHTML = `${grid}${ticks}<path d="${path}" fill="none" stroke="#416ddd" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>${warningPoints}<g id="hover-marker" visibility="hidden"><line id="hover-line" y1="${bounds.top}" y2="${bounds.bottom}" stroke="#acbddf" stroke-dasharray="3 4"/><circle id="hover-dot" r="4" fill="#416ddd" stroke="white" stroke-width="2"/></g>`;
  if (!layer.parentElement) $('#history-chart').append(layer);
  $('#plotted-column').textContent = METRICS[state.metric].label;
  $('#plotted-body').innerHTML = rows
    .slice(-12)
    .map(
      (row) =>
        `<tr><td>${row.date}</td><td class="numeric">${metricValue(row[state.metric], state.metric)}</td><td>${escapeHTML(row._warnings.join(', ') || '—')}</td></tr>`,
    )
    .join('');
}

function chartHover(index) {
  const point = state.chart.points.find((item) => item.index === index);
  const marker = $('#hover-marker');
  if (!point) {
    marker.setAttribute('visibility', 'hidden');
    $('#chart-tooltip').hidden = true;
    return;
  }
  state.hoverIndex = index;
  marker.setAttribute('visibility', 'visible');
  $('#hover-line').setAttribute('x1', point.x);
  $('#hover-line').setAttribute('x2', point.x);
  $('#hover-dot').setAttribute('cx', point.x);
  $('#hover-dot').setAttribute('cy', point.y);
  const tooltip = $('#chart-tooltip');
  tooltip.innerHTML = `<small>${dateLabel(point.row.date)}</small><strong>${metricValue(point.value, state.metric)}</strong>${point.row._warnings.length ? `<small>${escapeHTML(point.row._warnings.join(' · '))}</small>` : ''}`;
  tooltip.style.left = `${point.x < 570 ? Math.max(10, (point.x / 900) * 100 + 2) : Math.min(70, (point.x / 900) * 100 - 23)}%`;
  tooltip.hidden = false;
}

function renderPublication() {
  const failed = $('#publication-failure').checked && state.publication === 2;
  pressed('[data-publication]', 'data-publication', state.publication);
  const descriptions = [
    [
      'Previous version remains active',
      'Write prices, quarantine, and reports into a unique temporary directory. Researchers continue reading the previous complete version.',
    ],
    [
      'New snapshot is complete, not active',
      'Finish and fsync the artifacts. Move the complete version into immutable storage. The active manifest still points to the previous version.',
    ],
    [
      'CURRENT.json → new complete version',
      'Replace the small manifest using same-filesystem os.replace. New readers resolve the new version; existing readers retain their original snapshot.',
    ],
  ];
  const [title, text] = failed
    ? [
        'Previous version stays active',
        'An error before the manifest switch prevents publication. Only the new run’s staging artifacts are removed. The previously published data remains available.',
      ]
    : descriptions[state.publication];
  $('#publication-state').innerHTML =
    `<div class="pointer-display${failed ? ' failed' : state.publication === 2 ? ' complete' : ''}"><div><span>CURRENT.json</span><span>${failed ? 'PUBLICATION FAILED' : state.publication === 2 ? 'SWITCH COMPLETE' : 'UNCHANGED'}</span></div><strong>${title}</strong></div><p>${text}</p>`;
}

const QUERY_EXPLANATIONS = {
  security_summary: [
    'How does each security look in 2025?',
    'Group observations by security and source. Summarize average price return, return volatility, volume, and approximate dollar volume.',
  ],
  daily_returns: [
    'What happened from one observation to the next?',
    'Inspect closing prices, simple returns, and log returns in January 2025. Stored calculations retain the history needed before the date filter.',
  ],
  rolling_volatility: [
    'How has recent variability changed?',
    'Retrieve the trailing 20- and 30-return volatility estimates and 20-observation average volume. Each window uses only its own symbol/source history.',
  ],
};

function renderQuery() {
  const query = evidence.queries.find((item) => item.id === state.query);
  pressed('[data-query]', 'data-query', state.query);
  $('#sql-code').textContent = query.sql;
  $('#query-question').textContent = QUERY_EXPLANATIONS[state.query][0];
  $('#query-description').textContent = QUERY_EXPLANATIONS[state.query][1];
  $('#query-count').textContent =
    `${integer.format(query.row_count)} result rows · first ${query.rows.length} shown`;
  $('#query-head').innerHTML =
    `<tr>${query.columns.map((column) => `<th>${escapeHTML(column)}</th>`).join('')}</tr>`;
  $('#query-body').innerHTML = query.rows
    .map(
      (row) =>
        `<tr>${query.columns.map((column) => `<td${typeof row[column] === 'number' ? ' class="numeric"' : ''} title="${escapeHTML(row[column])}">${escapeHTML(plainValue(row[column], column))}</td>`).join('')}</tr>`,
    )
    .join('');
}

const WORKLOAD_NAMES = {
  A_csv_ingestion: 'CSV ingestion',
  B_group_by: 'Grouped means',
  C_rolling: 'Rolling volatility',
  D_filter_aggregate: 'Filter + aggregate',
  E_parquet_query: 'Parquet SQL query',
};

function renderBenchmarks() {
  const report = evidence.benchmarks[state.scale];
  const pairs = benchmarkPairs(report);
  const memory = state.benchmarkMetric === 'rss';
  pressed('[data-scale]', 'data-scale', state.scale);
  pressed('[data-benchmark-metric]', 'data-benchmark-metric', state.benchmarkMetric);
  $('#benchmark-title').textContent = memory
    ? 'Sampled whole-process peak RSS'
    : 'Median elapsed time';
  $('#benchmark-rows').innerHTML = pairs
    .map(({ workload, baseline, candidate }) => {
      const field = memory ? 'median_sampled_peak_rss_bytes' : 'median_wall_seconds';
      const values = [baseline[field], candidate[field]];
      const largest = Math.max(...values);
      const format = (value) =>
        memory ? `${number(value / 2 ** 20, 1)} MiB` : `${number(value * 1000, 2)} ms`;
      return `<div class="benchmark-row"><div class="benchmark-workload"><strong>${WORKLOAD_NAMES[workload]}</strong><span>${candidate.engine === 'polars' ? 'Polars vs pandas' : 'DuckDB vs pandas'}</span></div><div class="benchmark-bars"><div class="benchmark-bar-row"><div class="benchmark-track"><span style="width:${(values[0] / largest) * 100}%"></span></div><span>${format(values[0])}</span></div><div class="benchmark-bar-row candidate"><div class="benchmark-track"><span style="width:${Math.max(0.5, (values[1] / largest) * 100)}%"></span></div><span>${format(values[1])}</span></div></div><div class="benchmark-ratio${memory ? ' rss' : ''}"><strong>${memory ? `${number(values[1] / values[0], 2)}×` : `${number(candidate.speedup_vs_pandas, 2)}×`}</strong><span>${memory ? 'baseline RSS' : 'wall speedup'}</span></div></div>`;
    })
    .join('');
  const csv = pairs[0];
  const ratio =
    csv.candidate.median_sampled_peak_rss_bytes / csv.baseline.median_sampled_peak_rss_bytes;
  $('#benchmark-reading').innerHTML = memory
    ? `<strong>Faster doesn’t automatically mean less memory.</strong> In this ${Number(state.scale) / 1000}k-row CSV measurement, Polars’ sampled peak was ${number(csv.candidate.median_sampled_peak_rss_bytes / 2 ** 20, 1)} MiB versus pandas’ ${number(csv.baseline.median_sampled_peak_rss_bytes / 2 ** 20, 1)} MiB. ${ratio > 1 ? 'Polars used a higher sampled peak here.' : 'Polars used a lower sampled peak here.'} RSS includes inputs, imports, and allocator retention.`
    : `<strong>Read the scope with the number.</strong> CSV includes loading. Grouped means, rolling statistics, and the in-memory filter exclude preloading. Parquet compares PyArrow pushdown in pandas with direct DuckDB SQL. These are measured workload-specific results, not a universal speed guarantee.`;
  $('#benchmark-scope').textContent =
    `${report.hardware.logical_cpus} ${report.hardware.machine} CPUs · ${number(report.hardware.physical_memory_bytes / 2 ** 30, 0)} GiB RAM · Python ${report.python} · ${report.repetitions} repetitions`;
  $('#benchmark-download').href = `assets/measured-${state.scale}.json`;
}

function downloadText(text, file, type = 'text/csv') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = file;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 500);
}

let toastTimer;
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $('#toast').hidden = true;
  }, 2800);
}

function connectEvents() {
  document.addEventListener('click', (event) => {
    const target = event.target.closest('button');
    if (!target) return;
    if (target.dataset.recordFilter) {
      state.recordFilter = target.dataset.recordFilter;
      renderRecords();
    }
    if (target.dataset.inspect) inspectRecord(Number(target.dataset.inspect));
    if (target.dataset.policy) renderPolicy(target.dataset.policy);
    if (target.dataset.metric) {
      state.metric = target.dataset.metric;
      renderChart();
    }
    if (target.dataset.publication !== undefined) {
      state.publication = Number(target.dataset.publication);
      renderPublication();
    }
    if (target.dataset.query) {
      state.query = target.dataset.query;
      renderQuery();
    }
    if (target.dataset.scale) {
      state.scale = target.dataset.scale;
      renderBenchmarks();
    }
    if (target.dataset.benchmarkMetric) {
      state.benchmarkMetric = target.dataset.benchmarkMetric;
      renderBenchmarks();
    }
  });
  $('#warning-threshold').addEventListener('change', updateThreshold);
  for (const selector of ['#previous-price', '#current-price'])
    $(selector).addEventListener('input', updateCalculator);
  $('#chart-symbol').addEventListener('change', (event) => {
    state.symbol = event.target.value;
    renderChart();
  });
  $('#chart-range').addEventListener('change', (event) => {
    state.range = event.target.value;
    renderChart();
  });
  $('#publication-failure').addEventListener('change', renderPublication);
  $('#close-record').addEventListener('click', () => $('#record-dialog').close());
  $('#record-dialog').addEventListener('click', (event) => {
    if (event.target !== $('#record-dialog')) return;
    const rect = event.target.getBoundingClientRect();
    if (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    )
      event.target.close();
  });
  $('#print-page').addEventListener('click', () => window.print());
  $('#copy-sql').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText($('#sql-code').textContent);
      toast('SQL copied to clipboard.');
    } catch {
      toast('Clipboard unavailable. Select the SQL text to copy it.');
    }
  });
  $('#download-chart').addEventListener('click', () =>
    downloadText(
      csvText(state.history, [
        'date',
        'close',
        'simple_return',
        'log_return',
        'realized_vol_20',
        'realized_vol_30',
        'average_volume_20',
        'dollar_volume',
        '_source_row',
        '_warnings',
      ]),
      `${state.symbol}-${state.range}-synthetic.csv`,
    ),
  );
  $('#chart-wrap').addEventListener('pointermove', (event) => {
    const rect = $('#history-chart').getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 900;
    const { left, right } = state.chart.bounds;
    chartHover(
      Math.round(
        Math.max(0, Math.min(1, (x - left) / (right - left))) * (state.history.length - 1),
      ),
    );
  });
  $('#chart-wrap').addEventListener('pointerleave', () => {
    $('#chart-tooltip').hidden = true;
    $('#hover-marker').setAttribute('visibility', 'hidden');
  });
  $('#chart-wrap').addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const points = state.chart.points;
    if (!points.length) return;
    const current = points.findIndex((point) => point.index === state.hoverIndex);
    const next = Math.max(
      0,
      Math.min(points.length - 1, current + (event.key === 'ArrowRight' ? 1 : -1)),
    );
    chartHover(points[next].index);
  });
}

function connectNavigation() {
  const stages = $$('.stage');
  let scheduled = false;
  const update = () => {
    const span = document.documentElement.scrollHeight - innerHeight;
    $('#reading-progress').style.width =
      `${span > 0 ? Math.max(0, Math.min(100, (scrollY / span) * 100)) : 0}%`;
    let id = null;
    for (const stage of stages) {
      if (stage.getBoundingClientRect().top <= 180) id = stage.id;
      else break;
    }
    $$('#step-nav a').forEach((link) => {
      const active = link.dataset.stage === id;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'step');
      else link.removeAttribute('aria-current');
    });
    scheduled = false;
  };
  addEventListener(
    'scroll',
    () => {
      if (!scheduled) {
        scheduled = true;
        requestAnimationFrame(update);
      }
    },
    { passive: true },
  );
  addEventListener('resize', update);
  update();
}

async function init() {
  try {
    const response = await fetch(new URL('./assets/evidence.json', import.meta.url));
    if (!response.ok) throw new Error(`Evidence request returned ${response.status}`);
    evidence = await response.json();
    if (evidence.schema_version !== 1) throw new Error('Unsupported evidence format.');
    const report = evidence.report;
    if (report.input_row_count !== report.valid_row_count + report.quarantined_row_count)
      throw new Error('Row accounting does not reconcile.');
    const counts = {
      input: report.input_row_count,
      valid: report.valid_row_count,
      quarantine: report.quarantined_row_count,
    };
    $$('[data-stat]').forEach((element) => {
      element.textContent = integer.format(counts[element.dataset.stat]);
    });
    const exported = dateLabel(evidence.generated_at.slice(0, 10));
    $('#snapshot-notice>span:nth-child(2)').textContent =
      `Recorded Python pipeline · exported ${exported} · all market observations are synthetic`;
    Object.entries(evidence.source).forEach(([key, source]) => {
      $$(`[data-source="${key}"]`).forEach((link) => {
        link.href = source.url;
      });
      $$(`[data-code="${key}"] code`).forEach((code) => {
        code.textContent = source.code;
      });
    });
    $('#input-hash').textContent = report.input_files[0].sha256;
    $('#snapshot-version').textContent = evidence.snapshot.version;
    const verification = evidence.verification;
    if (verification.status === 'passed') {
      $('#verification-heading').textContent = `${verification.passed} Python tests passed`;
      $('#verification-details').textContent =
        `Recorded ${dateLabel(verification.recorded_at.slice(0, 10))} · ${verification.failures} failures · ${verification.skipped} skipped. Covers financial references, source boundaries, idempotency, failure recovery, SQL restrictions, and the CLI demo. Browser checks are reported separately.`;
    }
    renderInput();
    renderRules();
    renderPolicy('quarantine');
    renderRecords();
    updateThreshold();
    updateCalculator();
    renderChart();
    renderPublication();
    renderQuery();
    renderBenchmarks();
    connectEvents();
    connectNavigation();
    document.documentElement.dataset.ready = 'true';
  } catch (error) {
    $('#snapshot-notice>span:nth-child(2)').textContent =
      'Recorded evidence could not be loaded. Serve this page over HTTP and verify the exported assets.';
    $('#snapshot-notice').setAttribute('role', 'alert');
    document.documentElement.dataset.ready = 'error';
    console.error(error);
  }
}

init();
