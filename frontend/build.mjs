import { cpSync, mkdirSync, readFileSync, rmSync } from "node:fs";

const evidence = JSON.parse(
  readFileSync(new URL("./assets/evidence.json", import.meta.url), "utf8"),
);
if (
  evidence.report.input_row_count !==
  evidence.report.valid_row_count + evidence.report.quarantined_row_count
) {
  throw new Error(
    "Evidence row accounting does not reconcile. Re-export from Python.",
  );
}
const securities = evidence.workspace.securities;
if (
  securities.reduce((total, security) => total + security.rows, 0) !==
  evidence.report.valid_row_count
) {
  throw new Error("Workspace histories do not reconcile with retained rows.");
}
for (const security of securities) {
  const rows = JSON.parse(
    readFileSync(new URL(`./assets/${security.path}`, import.meta.url), "utf8"),
  );
  if (
    rows.length !== security.rows ||
    rows.some(
      (row) => row.symbol !== security.symbol || row.source !== security.source,
    )
  ) {
    throw new Error(`Workspace history is inconsistent: ${security.path}`);
  }
}
const destination = new URL("./dist/", import.meta.url);
rmSync(destination, { recursive: true, force: true });
mkdirSync(destination, { recursive: true });
for (const file of [
  "index.html",
  "workspace.html",
  "styles.css",
  "app.mjs",
  "workspace.mjs",
  "view.mjs",
  "model.mjs",
]) {
  cpSync(new URL(file, import.meta.url), new URL(file, destination));
}
cpSync(new URL("./assets/", import.meta.url), new URL("assets/", destination), {
  recursive: true,
});
console.log(
  `Built static walkthrough with ${evidence.report.valid_row_count.toLocaleString()} real Python-validated synthetic observations.`,
);
