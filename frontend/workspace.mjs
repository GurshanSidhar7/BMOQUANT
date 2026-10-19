import {
  ERROR_LABELS,
  WARNING_LABELS,
  METRICS,
  dateRangeError,
  researchSlice,
  summarizeSlice,
  csvText,
  RESEARCH_COLUMNS,
} from "./model.mjs";
import {
  $,
  integer,
  escapeHTML,
  percent,
  money,
  metricValue,
  fetchJSON,
  download,
  drawChart,
} from "./view.mjs";

const state = {
  evidence: null,
  rows: [],
  security: null,
  start: "",
  end: "",
  page: 0,
  metric: "close",
  request: 0,
  applied: false,
};
const cache = new Map();
const PAGE_SIZE = 15;
function showError(message) {
  $("#selection-error").textContent = message;
  $("#selection-error").hidden = !message;
}
function dirty() {
  if (!state.evidence) return;
  $("#selection-note").hidden = false;
  $("#download-csv").disabled = true;
  state.applied = false;
  showError("");
}
function renderSummary() {
  const summary = summarizeSlice(state.rows);
  $("#empty-state").hidden = !!summary;
  for (const id of ["#chart-surface", "#observations-surface"])
    $(id).hidden = !summary;
  $("#summary-cards").innerHTML = summary
    ? [
        [
          "Price change",
          `${summary.priceChange > 0 ? "+" : ""}${percent(summary.priceChange)}`,
          "First to last selected close",
        ],
        [
          "Recent volatility",
          percent(summary.latestVolatility),
          "20 returns · annualized · latest row",
        ],
        [
          "Average daily volume",
          summary.meanVolume === null
            ? "Unavailable"
            : integer(summary.meanVolume),
          state.security.has_volume
            ? "Shares per retained observation"
            : "Spot source supplies no trading volume",
        ],
        [
          "Retained observations",
          integer(summary.observations),
          `${summary.warningRows} ${summary.warningRows === 1 ? "row has" : "rows have"} review flags`,
        ],
      ]
        .map(
          ([label, value, detail]) =>
            `<article class="summary-card"><span>${label}</span><strong>${escapeHTML(value)}</strong><small>${escapeHTML(detail)}</small></article>`,
        )
        .join("")
    : "";
  const source = state.security.source;
  $("#results-title").textContent =
    `${state.security.name} / Price-history review`;
  $("#result-context").textContent = summary
    ? `${source} · ${summary.start} to ${summary.end} · ${integer(summary.observations)} retained rows`
    : `${source} · requested ${state.start} to ${state.end} · 0 retained rows`;
  $("#download-csv").disabled = !summary;
  renderInstrument();
  renderQuality();
  if (summary) {
    renderChart();
    renderTable();
  }
}
function renderInstrument() {
  const security = state.security;
  const real = security.data_kind === "real";
  $("#price-column-label").textContent =
    security.instrument_type === "commodity_spot"
      ? "Spot price / barrel"
      : "Close";
  $("#instrument-details").innerHTML =
    `<div><span class="tag ${real ? "good" : "warn"}">${real ? "REAL HISTORICAL DATA" : "SYNTHETIC TEST FIXTURE"}</span><h3>${escapeHTML(security.name)}</h3><p>${escapeHTML(security.price_basis)}</p><p class="caption">${escapeHTML(security.provider)} · ${escapeHTML(security.unit)} · ${security.start} to ${security.end}${real ? ` · retrieved ${security.retrieved_at.slice(0, 10)}` : ""}</p></div><div class="download-links">${real ? `<a href="${escapeHTML(security.source_url)}" target="_blank" rel="noopener">Provider source ↗</a>` : ""}<a href="assets/${escapeHTML(security.input_path)}" download>${real ? "Input CSV" : "Input excerpt"} ↓</a></div>`;
}
function renderChart() {
  $("#chart-title").textContent = METRICS[state.metric].label;
  $("#chart-description").textContent =
    state.metric === "realized_vol_20"
      ? "Variation in the last 20 log returns · annualized · recorded Python values"
      : state.metric === "simple_return"
        ? "Change from the previous retained close · recorded Python values"
        : `${state.security.instrument_type === "commodity_spot" ? "WTI Cushing spot price" : "Closing price"} · ${state.security.unit} · ${state.security.data_kind === "real" ? "real historical observations" : "generated test data"}`;
  $("#chart-readout").textContent =
    "Focus the chart and use ← or → to inspect an observation.";
  drawChart($("#chart-container"), state.rows, state.metric);
}
function renderTable() {
  const pageCount = Math.ceil(state.rows.length / PAGE_SIZE);
  const offset = state.page * PAGE_SIZE;
  const rows = state.rows.slice(offset, offset + PAGE_SIZE);
  $("#observations-body").innerHTML = rows
    .map(
      (row) =>
        `<tr><td>${row.date}</td><td>${money(row.close)}</td><td>${percent(row.simple_return)}</td><td>${percent(row.realized_vol_20)}</td><td>${row.volume === null ? "—" : integer(row.volume)}</td><td class="reasons">${row._warnings.length ? `<button class="inspect-button" data-warning-row="${row._source_row}">${row._warnings.length} ${row._warnings.length === 1 ? "flag" : "flags"} · inspect ↗</button>` : '<span class="muted">—</span>'}</td><td>${integer(row._source_row)}</td></tr>`,
    )
    .join("");
  $("#table-count").textContent =
    `Rows ${offset + 1}–${Math.min(offset + PAGE_SIZE, state.rows.length)} of ${integer(state.rows.length)}`;
  $("#page-status").textContent = `Page ${state.page + 1} of ${pageCount}`;
  $("#previous-page").disabled = state.page === 0;
  $("#next-page").disabled = state.page >= pageCount - 1;
}
async function applySelection(event) {
  event?.preventDefault();
  const start = $("#start-date").value,
    end = $("#end-date").value;
  const error = dateRangeError(start, end);
  if (error) {
    showError(error);
    return;
  }
  const security =
    state.evidence.workspace.securities[Number($("#security-select").value)];
  const request = ++state.request;
  state.applied = false;
  $("#apply-selection").disabled = true;
  $("#apply-selection").textContent = "Loading history…";
  $("#research-results").setAttribute("aria-busy", "true");
  $("#download-csv").disabled = true;
  showError("");
  try {
    if (!cache.has(security.path))
      cache.set(
        security.path,
        fetchJSON(`assets/${security.path}`).catch((error) => {
          cache.delete(security.path);
          throw error;
        }),
      );
    const all = await cache.get(security.path);
    if (request !== state.request) return;
    state.rows = researchSlice(all, start, end);
    state.security = security;
    state.start = start;
    state.end = end;
    state.page = 0;
    state.applied = true;
    $("#selection-note").hidden = true;
    renderSummary();
    // Controls may have changed while the selected history was loading.
    if (
      $("#start-date").value !== start ||
      $("#end-date").value !== end ||
      state.evidence.workspace.securities[
        Number($("#security-select").value)
      ] !== security
    )
      dirty();
  } catch (error) {
    if (request === state.request) {
      showError(
        `Could not load this selection. ${error.message} Try applying again.`,
      );
      $("#selection-note").hidden = false;
    }
  } finally {
    if (request === state.request) {
      $("#apply-selection").disabled = false;
      $("#apply-selection").textContent = "Apply selection";
      $("#research-results").setAttribute("aria-busy", "false");
    }
  }
}
function renderQuality() {
  const dataset = state.evidence.datasets[state.security.dataset_id];
  const report = dataset.report;
  $("#quality-title").textContent = dataset.title;
  $("#quality-context").textContent = dataset.description;
  $("#quality-download").href = `assets/${dataset.report_path}`;
  $("#quarantine-count").textContent =
    `${report.quarantined_row_count} quarantined records · this source dataset`;
  const warningFlags = Object.values(report.warning_counts).reduce(
    (total, count) => total + count,
    0,
  );
  $("#quality-summary").innerHTML =
    `<span><strong>${integer(report.input_row_count)}</strong> input rows</span><span><strong>${integer(report.valid_row_count)}</strong> retained</span><span><strong>${report.quarantined_row_count}</strong> set aside</span><span class="quality-warning"><strong>${warningFlags}</strong> warning flags on retained data</span>`;
  const bad = dataset.records.filter((row) => row.status === "quarantined");
  $("#quarantine-body").innerHTML = bad.length
    ? bad
        .map(
          (row) =>
            `<tr><td>${integer(row.row)}</td><td>${escapeHTML(row.raw.ticker ?? "Missing")}</td><td>${escapeHTML(row.raw.trade_date)}</td><td>${escapeHTML(row.raw.close)}</td><td class="reasons">${row.errors.map((code) => escapeHTML(ERROR_LABELS[code] ?? code)).join("; ")}</td><td><button class="inspect-button" data-record-row="${row.row}" aria-label="Inspect quarantined source row ${row.row}">Inspect ↗</button></td></tr>`,
        )
        .join("")
    : '<tr><td colspan="6" class="muted">No records were quarantined in this sample. Synthetic examples remain available to inspect deliberate errors.</td></tr>';
}
function inspectQuarantine(rowNumber) {
  const row = state.evidence.datasets[state.security.dataset_id].records.find(
    (record) => record.row === rowNumber,
  );
  if (!row) return;
  $("#record-title").textContent = `Quarantined row ${integer(row.row)}`;
  $("#record-content").innerHTML =
    `<span class="tag bad">SET ASIDE FOR REVIEW</span><p style="margin-top:15px">${row.errors.map((code) => escapeHTML(ERROR_LABELS[code] ?? code)).join("; ")}.</p><dl><dt>Original file</dt><dd>${escapeHTML(row.file)}</dd><dt>Source row</dt><dd>${integer(row.row)}</dd><dt>Parsing errors</dt><dd>${escapeHTML(row.parse_errors.join(", ") || "None")}</dd></dl><h3>Original values from the CSV</h3><pre>${escapeHTML(JSON.stringify(row.raw, null, 2))}</pre><p>Quarantined records are excluded from the price-history selection and its CSV download.</p>`;
  $("#record-dialog").showModal();
}
function inspectWarning(rowNumber) {
  const row = state.rows.find((record) => record._source_row === rowNumber);
  if (!row) return;
  $("#record-title").textContent = `Retained row ${integer(row._source_row)}`;
  $("#record-content").innerHTML =
    `<span class="tag warn">WARNING · KEPT IN THE DATASET</span><p style="margin-top:15px">${row._warnings.map((code) => escapeHTML(WARNING_LABELS[code] ?? code)).join("; ")}.</p><dl><dt>Stock</dt><dd>${escapeHTML(row.symbol)}</dd><dt>Source</dt><dd>${escapeHTML(row.source)}</dd><dt>Date</dt><dd>${row.date}</dd><dt>Close</dt><dd>${money(row.close)}</dd><dt>Price return</dt><dd>${percent(row.simple_return)}</dd><dt>Volume</dt><dd>${row.volume === null ? "Not supplied" : integer(row.volume)}</dd><dt>Source row</dt><dd>${integer(row._source_row)}</dd></dl><p>A warning requests review; it does not identify the cause or automatically discard the record. The source row refers to ${escapeHTML(state.security.file)}.</p>`;
  $("#record-dialog").showModal();
}
$("#research-form").addEventListener("submit", applySelection);
for (const id of ["#security-select", "#start-date", "#end-date"])
  $(id).addEventListener("input", dirty);
$("#metric-select").addEventListener("change", () => {
  state.metric = $("#metric-select").value;
  if (state.rows.length) renderChart();
});
$("#previous-page").addEventListener("click", () => {
  if (state.page > 0) {
    state.page--;
    renderTable();
  }
});
$("#next-page").addEventListener("click", () => {
  if ((state.page + 1) * PAGE_SIZE < state.rows.length) {
    state.page++;
    renderTable();
  }
});
$("#download-csv").addEventListener("click", () => {
  if (!state.applied || !state.rows.length) return;
  download(
    csvText(
      state.rows.map((row) => ({
        ...row,
        data_kind: state.security.data_kind,
        instrument_type: state.security.instrument_type,
        price_unit: state.security.unit,
      })),
      RESEARCH_COLUMNS,
    ),
    `${state.security.symbol}_${state.start}_${state.end}_${state.security.data_kind}.csv`,
  );
});
$("#reset-selection").addEventListener("click", () => {
  $("#security-select").value = String(
    state.evidence.workspace.securities.findIndex((s) => s.symbol === "NVDA"),
  );
  $("#start-date").value = "2025-07-01";
  $("#end-date").value = "2025-12-31";
  $("#metric-select").value = "close";
  state.metric = "close";
  applySelection();
});
$("#quarantine-body").addEventListener("click", (event) => {
  const button = event.target.closest("[data-record-row]");
  if (button) inspectQuarantine(Number(button.dataset.recordRow));
});
$("#observations-body").addEventListener("click", (event) => {
  const button = event.target.closest("[data-warning-row]");
  if (button) inspectWarning(Number(button.dataset.warningRow));
});
$("#close-record").addEventListener("click", () => $("#record-dialog").close());
async function initialize() {
  try {
    state.evidence = await fetchJSON("assets/evidence.json");
    const securities = state.evidence.workspace.securities;
    $("#security-select").innerHTML = ["real", "synthetic"]
      .map(
        (kind) =>
          `<optgroup label="${kind === "real" ? "Real historical samples" : "Synthetic tests · 10 stocks"}">${securities.map((security, index) => (security.data_kind === kind ? `<option value="${index}">${escapeHTML(security.name)} (${security.symbol})</option>` : "")).join("")}</optgroup>`,
      )
      .join("");
    $("#security-select").value = String(
      securities.findIndex((s) => s.symbol === "NVDA"),
    );
    for (const id of [
      "#security-select",
      "#start-date",
      "#end-date",
      "#apply-selection",
      "#reset-selection",
    ])
      $(id).disabled = false;
    $("#workspace-status").textContent =
      `3 real historical samples + 10 synthetic test stocks · ${integer(state.evidence.workspace.retained_rows)} retained observations · prepared ${state.evidence.generated_at.slice(0, 10)} · browser filters only`;
    await applySelection();
  } catch (error) {
    $("#workspace-status").textContent =
      `The saved dataset could not be loaded. ${error.message} Refresh to try again.`;
    $("#workspace-status").classList.add("error-message");
    $("#research-results").setAttribute("aria-busy", "false");
  }
}
initialize();
