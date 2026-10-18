import { chartGeometry, METRICS } from "./model.mjs";
export const $ = (selector) => document.querySelector(selector);
export const integer = (value) =>
  new Intl.NumberFormat("en-CA", { maximumFractionDigits: 0 }).format(value);
export const number = (value, digits = 2) =>
  new Intl.NumberFormat("en-CA", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
export const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const percent = (value) =>
  value === null || value === undefined ? "—" : `${number(value * 100)}%`;
export const money = (value) =>
  value === null || value === undefined ? "—" : `$${number(value)}`;
export function metricValue(value, metric, compact = false) {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  if (METRICS[metric]?.type === "percent")
    return `${number(value * 100, compact ? 1 : 2)}%`;
  return money(value);
}
export async function fetchJSON(path) {
  const response = await fetch(path);
  if (!response.ok)
    throw new Error(`Could not load ${path} (${response.status}).`);
  return response.json();
}
export function download(text, filename, type = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function drawChart(container, rows, metric) {
  const width = 1000,
    height = 290;
  const geometry = chartGeometry(rows, metric, width, height);
  if (!geometry.points.length) {
    container.innerHTML =
      '<div class="empty-state"><h3>No calculated values for this measure.</h3><p>Volatility needs at least 20 earlier returns. Try a later or wider date range.</p></div>';
    return null;
  }
  const { bounds, min, max, points, path } = geometry;
  const grid = Array.from({ length: 5 }, (_, i) => {
    const y = bounds.top + ((bounds.bottom - bounds.top) * i) / 4;
    const value = max - ((max - min) * i) / 4;
    return `<line class="chart-grid" x1="${bounds.left}" x2="${bounds.right}" y1="${y}" y2="${y}"/><text class="chart-axis" text-anchor="end" x="${bounds.left - 10}" y="${y + 4}">${escapeHTML(metricValue(value, metric, true))}</text>`;
  }).join("");
  const labels = [0, Math.floor((rows.length - 1) / 2), rows.length - 1]
    .filter((v, i, a) => a.indexOf(v) === i)
    .map(
      (index) =>
        `<text class="chart-axis" x="${bounds.left + (index / Math.max(1, rows.length - 1)) * (bounds.right - bounds.left)}" y="${height - 10}" text-anchor="${index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle"}">${rows[index].date}</text>`,
    )
    .join("");
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" tabindex="0" aria-label="${escapeHTML(METRICS[metric].label)} for ${rows.length} selected observations. Use left and right arrow keys to inspect values."><title>${escapeHTML(METRICS[metric].label)}</title>${grid}<path class="chart-line" d="${path}"/>${points.length === 1 ? `<circle cx="${points[0].x}" cy="${points[0].y}" r="4" fill="#2857d9"/>` : ""}${labels}<g id="chart-focus" hidden><line class="chart-crosshair" y1="${bounds.top}" y2="${bounds.bottom}"/><circle class="chart-dot" r="4"/></g></svg>`;
  const svg = container.querySelector("svg");
  let focused = points.length - 1;
  function inspect(index) {
    focused = Math.max(0, Math.min(points.length - 1, index));
    const p = points[focused];
    const focus = svg.querySelector("#chart-focus");
    focus.removeAttribute("hidden");
    focus.querySelector("line").setAttribute("x1", p.x);
    focus.querySelector("line").setAttribute("x2", p.x);
    focus.querySelector("circle").setAttribute("cx", p.x);
    focus.querySelector("circle").setAttribute("cy", p.y);
    $("#chart-readout").textContent =
      `${p.row.date} · ${METRICS[metric].label}: ${metricValue(p.value, metric)} · source row ${integer(p.row._source_row)}`;
  }
  svg.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    inspect(
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? points.length - 1
          : focused + (event.key === "ArrowLeft" ? -1 : 1),
    );
  });
  svg.addEventListener("focus", () => inspect(focused));
  svg.addEventListener("pointermove", (event) => {
    const rect = svg.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * width;
    let nearest = 0;
    for (let i = 1; i < points.length; i++)
      if (Math.abs(points[i].x - x) < Math.abs(points[nearest].x - x))
        nearest = i;
    inspect(nearest);
  });
  inspect(focused);
  return geometry;
}
