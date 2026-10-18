// Optional browser QA. Use a temporary Playwright installation to keep runtime dependencies at zero.
import assert from "node:assert/strict";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright"
);
const base = process.env.WALKTHROUGH_URL || "http://127.0.0.1:4173";
const output =
  process.env.WALKTHROUGH_SCREENSHOTS || "/tmp/research-data-walkthrough-qa";
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
    document.querySelector("#data-status").textContent.includes("65,201 input"),
  );
  await page.addStyleTag({ content: "html {scroll-behavior:auto!important}" });
  assert.equal(await page.locator(".stage[id]:not(#scope)").count(), 5);
  assert.equal(await page.locator("#raw-rows tr").count(), 4);
  assert.match(await page.locator("#row-accounting").textContent(), /65,194/);
  await page.screenshot({ path: path.join(output, "desktop-overview.png") });
  await page.locator("#current-close").fill("90");
  assert.equal(await page.locator("#return-result").textContent(), "-10.00%");
  await page.locator("#previous-close").fill("0");
  assert.match(await page.locator("#return-result").textContent(), /positive/);
  await page.locator("#previous-close").fill("100");
  await page.locator("#current-close").fill("102");
  await page.locator("#check").scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "desktop-validation.png") });
  checks.push(
    "Five-step explanation loads real records and row accounting; return example validates inputs",
  );
  await page.emulateMedia({ media: "print" });
  await page.pdf({
    path: path.join(output, "walkthrough.pdf"),
    format: "A4",
    printBackground: true,
  });
  await page.emulateMedia({ media: "screen" });
  await page.goto(`${base}/workspace.html`);
  await page.waitForFunction(() =>
    document
      .querySelector("#result-context")
      .textContent.includes("261 retained rows"),
  );
  assert.equal(await page.locator("#security-select option").count(), 50);
  assert.equal(await page.locator("#quarantine-body tr").count(), 7);
  assert.equal(await page.locator("#observations-body tr").count(), 15);
  await page.screenshot({ path: path.join(output, "desktop-workspace.png") });
  await page.locator("#metric-select").selectOption("realized_vol_20");
  assert.ok(
    (await page.locator("#chart-container .chart-line").getAttribute("d"))
      .length > 100,
  );
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
    /2025-01-01/,
  );
  await page.keyboard.press("ArrowRight");
  assert.match(
    await page.locator("#chart-readout").textContent(),
    /2025-01-02/,
  );
  const downloadEvent = page.waitForEvent("download");
  await page.locator("#download-csv").click();
  const download = await downloadEvent;
  assert.match(
    download.suggestedFilename(),
    /SYN0001_2025-01-01_2025-12-31_synthetic.csv/,
  );
  const csv = readFileSync(await download.path(), "utf8");
  assert.equal(csv.trim().split("\n").length, 262);
  assert.match(csv.split("\n")[0], /_source_row,_warnings/);
  await page.locator("#next-page").click();
  assert.match(
    await page.locator("#page-status").textContent(),
    /Page 2 of 18/,
  );
  await page.locator("#previous-page").click();
  checks.push(
    "All 50 stocks available; stored history, accessible chart, pagination, and full 261-row export work",
  );
  await page.locator("#start-date").fill("2025-12-31");
  await page.locator("#end-date").fill("2025-01-01");
  assert.ok(await page.locator("#download-csv").isDisabled());
  await page.locator("#apply-selection").click();
  assert.match(
    await page.locator("#selection-error").textContent(),
    /start date/,
  );
  await page.locator("#start-date").fill("2030-01-01");
  await page.locator("#end-date").fill("2030-12-31");
  await page.locator("#apply-selection").click();
  await page.waitForFunction(
    () => !document.querySelector("#empty-state").hidden,
  );
  assert.ok(await page.locator("#download-csv").isDisabled());
  assert.equal(await page.locator("#summary-cards .summary-card").count(), 0);
  await page.locator("#security-select").selectOption("0");
  await page.locator("#start-date").fill("2021-01-01");
  await page.locator("#end-date").fill("2021-02-28");
  await page.locator("#apply-selection").click();
  await page.waitForFunction(
    () =>
      document
        .querySelector("#results-title")
        .textContent.startsWith("SYN0000") &&
      !document.querySelector("#empty-state").hidden === false,
  );
  await page.locator("#metric-select").selectOption("close");
  await page.locator("#next-page").click();
  await page.locator("[data-warning-row]").first().click();
  assert.ok(await page.locator("#record-dialog").evaluate((d) => d.open));
  assert.match(
    await page.locator("#record-content").textContent(),
    /kept|Warning|warning/,
  );
  await page.keyboard.press("Escape");
  for (const row of ["12", "65202"]) {
    await page.locator(`[data-record-row="${row}"]`).click();
    assert.match(
      await page.locator("#record-content").textContent(),
      /Duplicate observation key/,
    );
    await page.keyboard.press("Escape");
  }
  checks.push(
    "Invalid and empty date ranges are handled; pending controls prevent stale downloads; warnings and both duplicate records inspect correctly",
  );
  await page.locator("#reset-selection").click();
  await page.waitForFunction(() =>
    document
      .querySelector("#result-context")
      .textContent.includes("261 retained rows"),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, "mobile-workspace.png") });
  for (const id of [
    "selection-title",
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
  await page.goto(base);
  await page.waitForFunction(() =>
    document.querySelector("#data-status").textContent.includes("65,201 input"),
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
    "Both pages fit a 390px mobile viewport without page-level overflow; walkthrough PDF renders",
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
