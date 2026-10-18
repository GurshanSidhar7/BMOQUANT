import { cpSync, mkdirSync, readFileSync, rmSync } from 'node:fs';

const evidence = JSON.parse(
  readFileSync(new URL('./assets/evidence.json', import.meta.url), 'utf8'),
);
if (
  evidence.report.input_row_count !==
  evidence.report.valid_row_count + evidence.report.quarantined_row_count
) {
  throw new Error('Evidence row accounting does not reconcile. Re-export from Python.');
}
const destination = new URL('./dist/', import.meta.url);
rmSync(destination, { recursive: true, force: true });
mkdirSync(destination, { recursive: true });
for (const file of ['index.html', 'styles.css', 'app.mjs', 'model.mjs']) {
  cpSync(new URL(file, import.meta.url), new URL(file, destination));
}
cpSync(new URL('./assets/', import.meta.url), new URL('assets/', destination), { recursive: true });
console.log(
  `Built static walkthrough with ${evidence.report.valid_row_count.toLocaleString()} real Python-validated synthetic observations.`,
);
