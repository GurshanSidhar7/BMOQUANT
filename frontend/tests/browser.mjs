// Optional QA uses a temporary Playwright installation; no app runtime dependencies.
import assert from "node:assert/strict";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright"
);
const base = process.env.WALKTHROUGH_URL || "http://127.0.0.1:4173";
const output =
  process.env.WALKTHROUGH_SCREENSHOTS || "/tmp/research-data-walkthrough-qa";
const evidence = JSON.parse(
  readFileSync(new URL("../assets/evidence.json", import.meta.url), "utf8"),
);
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({
  ...(process.env.CHROME_EXECUTABLE
    ? { executablePath: process.env.CHROME_EXECUTABLE }
    : {}),
  headless: true,
});
const errors = [],
  checks = [];
try {
  const page = await browser.newPage({
    viewport: { width: 1512, height: 1050 },
    deviceScaleFactor: 1,
  });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  assert.equal((await page.goto(base)).status(), 200);
  await page.waitForFunction(() =>
    document.querySelector("#data-status").textContent.includes("13,041 input"),
  );
  await page.addStyleTag({ content: "html {scroll-behavior:auto!important}" });
  assert.equal(await page.locator(".stage[id]:not(#scope)").count(), 5);
  assert.match(await page.locator("#row-accounting").textContent(), /13,034/);
  await page.screenshot({ path: path.join(output, "desktop-overview.png") });
  await page.locator("#current-close").fill("90");
  assert.equal(await page.locator("#return-result").textContent(), "-10.00%");
  await page.locator("#previous-close").fill("0");
  assert.match(await page.locator("#return-result").textContent(), /positive/);
  await page.locator("#previous-close").fill("100");
  await page.locator("#current-close").fill("102");
  await page.locator("#check").scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "desktop-validation.png") });
  await page.emulateMedia({ media: "print" });
  await page.pdf({
    path: path.join(output, "walkthrough.pdf"),
    format: "A4",
    printBackground: true,
  });
  await page.emulateMedia({ media: "screen" });
  checks.push(
    "Five-step explanation uses the ten-stock fixture and reconciles all 13,041 rows",
  );
  await page.goto(`${base}/workspace.html`);
  await page.waitForFunction(() =>
    document.querySelector("#results-title").textContent.includes("NVIDIA"),
  );
  await page.waitForFunction(
    () =>
      document.querySelector("#research-results").getAttribute("aria-busy") ===
      "false",
  );
  assert.equal(await page.locator("#security-select option").count(), 13);
  assert.equal(
    await page
      .locator(
        '#security-select optgroup[label="Synthetic tests · 10 stocks"] option',
      )
      .count(),
    10,
  );
  await page.screenshot({ path: path.join(output, "desktop-workspace.png") });
  async function select(symbol, start = "2025-07-01", end = "2025-12-31") {
    const index = evidence.workspace.securities.findIndex(
      (s) => s.symbol === symbol,
    );
    await page.locator("#security-select").selectOption(String(index));
    await page.locator("#start-date").fill(start);
    await page.locator("#end-date").fill(end);
    assert.ok(await page.locator("#download-csv").isDisabled());
    await page.locator("#apply-selection").click();
    await page.waitForFunction(
      () =>
        document
          .querySelector("#research-results")
          .getAttribute("aria-busy") === "false",
    );
  }
  for (const symbol of ["NVDA", "SNDK", "WTI"]) {
    await select(symbol);
    const security = evidence.workspace.securities.find(
      (s) => s.symbol === symbol,
    );
    const history = JSON.parse(
      readFileSync(
        new URL(`../assets/${security.path}`, import.meta.url),
        "utf8",
      ),
    );
    const expected = history.filter(
      (r) => r.date >= "2025-07-01" && r.date <= "2025-12-31",
    );
    assert.match(
      await page.locator("#instrument-details").textContent(),
      /REAL HISTORICAL DATA/,
    );
    assert.equal(
      await page.locator("#instrument-details a").first().getAttribute("href"),
      security.source_url,
    );
    assert.equal(await page.locator("[data-record-row]").count(), 0);
    assert.match(
      await page.locator("#quarantine-body").textContent(),
      /No records were quarantined/,
    );
    await page.locator("#metric-select").selectOption("realized_vol_20");
    assert.notEqual(
      await page
        .locator("#observations-body tr:first-child td:nth-child(4)")
        .textContent(),
      "—",
    );
    await page.locator("#chart-container svg").focus();
    await page.keyboard.press("Home");
    assert.match(
      await page.locator("#chart-readout").textContent(),
      /2025-07-01/,
    );
    const downloadEvent = page.waitForEvent("download");
    await page.locator("#download-csv").click();
    const download = await downloadEvent;
    assert.equal(
      download.suggestedFilename(),
      `${symbol}_2025-07-01_2025-12-31_real.csv`,
    );
    const csv = readFileSync(await download.path(), "utf8");
    assert.equal(csv.trim().split("\n").length, expected.length + 1);
    assert.match(csv.split("\n")[0], /data_kind,instrument_type,price_unit/);
    const fields = csv.trim().split("\n")[1].split(",");
    assert.equal(fields[0], symbol);
    assert.equal(Number(fields[9]), expected[0].close);
    if (symbol === "WTI") {
      assert.match(
        await page.locator("#instrument-details").textContent(),
        /USD per barrel/,
      );
      assert.match(
        await page.locator("#summary-cards").textContent(),
        /Unavailable/,
      );
      assert.equal(
        await page
          .locator("#observations-body tr:first-child td:nth-child(5)")
          .textContent(),
        "—",
      );
      assert.equal(fields[3], "commodity_spot");
      assert.equal(fields[6], "");
      assert.equal(fields[7], "");
      assert.equal(fields[8], "");
      assert.equal(fields[10], "");
      await page.screenshot({ path: path.join(output, "desktop-wti.png") });
    }
    await page.locator("#next-page").click();
    assert.match(await page.locator("#page-status").textContent(), /Page 2/);
  }
  checks.push(
    "NVDA, SNDK, and WTI render actual saved history, prior volatility, source links, and complete typed CSV exports; WTI has no invented OHLC or volume",
  );
  await select("SNDK", "2024-01-01", "2024-12-31");
  assert.ok(await page.locator("#empty-state").isVisible());
  assert.ok(await page.locator("#download-csv").isDisabled());
  await page.locator("#start-date").fill("2025-12-31");
  await page.locator("#end-date").fill("2025-01-01");
  await page.locator("#apply-selection").click();
  assert.match(
    await page.locator("#selection-error").textContent(),
    /start date/,
  );
  await select("SYN0000", "2021-01-01", "2021-02-28");
  assert.match(
    await page.locator("#instrument-details").textContent(),
    /SYNTHETIC TEST FIXTURE/,
  );
  assert.equal(await page.locator("[data-record-row]").count(), 7);
  await page.locator("[data-warning-row]").first().click();
  assert.ok(await page.locator("#record-dialog").evaluate((d) => d.open));
  await page.keyboard.press("Escape");
  for (const row of ["12", "13042"]) {
    await page.locator(`[data-record-row="${row}"]`).click();
    assert.match(
      await page.locator("#record-content").textContent(),
      /Duplicate observation key/,
    );
    await page.keyboard.press("Escape");
  }
  checks.push(
    "Pre-listing and invalid ranges stay empty/actionable; synthetic review switches reports and preserves all seven error records and both duplicate members",
  );
  await page.locator("#reset-selection").click();
  await page.waitForFunction(() =>
    document.querySelector("#results-title").textContent.includes("NVIDIA"),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "mobile-workspace.png") });
  for (const id of [
    "selection-title",
    "instrument-details",
    "results-title",
    "chart-surface",
    "observations-surface",
    "quality-title",
  ]) {
    await page.locator(`#${id}`).scrollIntoViewIfNeeded();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
      `${id} overflows`,
    );
  }
  await select("WTI");
  await page.locator("#instrument-details").scrollIntoViewIfNeeded();
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  );
  await page.screenshot({ path: path.join(output, "mobile-wti.png") });
  await page.goto(base);
  await page.waitForFunction(() =>
    document.querySelector("#data-status").textContent.includes("13,041 input"),
  );
  await page.screenshot({ path: path.join(output, "mobile-overview.png") });
  for (const id of [
    "read",
    "standardize",
    "check",
    "calculate",
    "save",
    "scope",
  ]) {
    await page.locator(`#${id}`).scrollIntoViewIfNeeded();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
      `${id} overflows`,
    );
  }
  checks.push(
    "Both pages and WTI fit the mobile viewport; keyboard inspection and walkthrough PDF work",
  );
  assert.deepEqual(errors, [], "Browser errors");
  console.log(
    JSON.stringify(
      { checks, browserErrors: errors, screenshots: output },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
