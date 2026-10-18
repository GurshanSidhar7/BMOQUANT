import { returnExample, ERROR_LABELS } from "./model.mjs";
import { $, integer, escapeHTML, percent, fetchJSON } from "./view.mjs";

function render(evidence) {
  const { report } = evidence;
  $("#data-status").textContent =
    `Recorded Python run · ${integer(report.input_row_count)} input records · 50 synthetic stocks · 2021–2025 · prepared ${evidence.generated_at.slice(0, 10)}`;
  const rawRows = [
    ...evidence.records.slice(0, 3),
    evidence.records.find((r) => r.row === 8),
  ];
  $("#raw-rows").innerHTML = rawRows
    .map(
      ({ raw, parse_errors }) =>
        `<tr><td${raw.ticker === null ? ' class="bad-cell"' : ""}>${escapeHTML(raw.ticker ?? "Missing")}</td><td${parse_errors.includes("date") ? ' class="bad-cell"' : ""}>${escapeHTML(raw.trade_date)}</td><td>${escapeHTML(raw.close)}</td><td${Number(raw.volume) < 0 ? ' class="bad-cell"' : ""}>${escapeHTML(raw.volume)}</td></tr>`,
    )
    .join("");
  $("#row-accounting").innerHTML =
    `<div><strong>${integer(report.input_row_count)}</strong><small>input records</small></div><span>=</span><div><strong>${integer(report.valid_row_count)}</strong><small>retained records</small></div><span>+</span><div><strong>${integer(report.quarantined_row_count)}</strong><small>set aside for review</small></div>`;
  const explain = {
    duplicate_key:
      "Both copies of the same stock, date, and source were set aside.",
    invalid_price: "A closing price was negative.",
    invalid_ohlc:
      "The closing price also fell outside the reported daily range.",
    malformed_value: "The text “not-a-date” could not be read as a date.",
    missing_value: "A stock identifier was missing.",
    negative_volume: "The number of traded shares was negative.",
    nonfinite_price: "One closing price was NaN: not a usable number.",
  };
  $("#error-examples").innerHTML = Object.entries(report.errors_by_category)
    .map(
      ([code, count]) =>
        `<div class="error-example"><div>${escapeHTML(ERROR_LABELS[code] ?? code)}<small>${escapeHTML(explain[code] ?? "Review the original input value.")}</small></div><strong>${count} ${count === 1 ? "row" : "rows"}</strong></div>`,
    )
    .join("");
  for (const link of document.querySelectorAll("[data-source]"))
    if (evidence.source[link.dataset.source])
      link.href = evidence.source[link.dataset.source].url;
  if (evidence.verification.status === "passed")
    $("#verification").textContent =
      `Recorded verification: ${evidence.verification.passed} Python tests passed on ${evidence.verification.recorded_at.slice(0, 10)}. This is a local test run; check GitHub Actions for hosted CI results.`;
}
function updateReturn() {
  const result = returnExample(
    Number($("#previous-close").value),
    Number($("#current-close").value),
  );
  $("#return-result").textContent = result
    ? `${result.simple > 0 ? "+" : ""}${percent(result.simple)}`
    : "Use positive prices";
}
$("#return-form").addEventListener("input", updateReturn);
$("#return-form").addEventListener("submit", (e) => e.preventDefault());
$("#print-page").addEventListener("click", () => window.print());
const observer = new IntersectionObserver(
  (entries) => {
    const visible = entries
      .filter((e) => e.isIntersecting)
      .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
    if (!visible.length) return;
    document.querySelectorAll("#step-nav a").forEach((link) => {
      const active = link.hash === `#${visible[0].target.id}`;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "step");
      else link.removeAttribute("aria-current");
    });
  },
  { rootMargin: "-20% 0px -55% 0px", threshold: 0 },
);
for (const section of document.querySelectorAll(".stage[id]"))
  if (section.id !== "scope") observer.observe(section);
fetchJSON("assets/evidence.json")
  .then(render)
  .catch((error) => {
    $("#data-status").textContent =
      `The recorded examples could not be loaded. ${error.message} Read the explanations below or try refreshing.`;
    $("#data-status").classList.add("error-message");
  });
