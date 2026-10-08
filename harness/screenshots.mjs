// Captures dashboard screenshots: Chinese page -> docs/img/ (REPORT.md),
// English page -> docs/img/en/ (README.md).
// Optional tooling: needs Playwright with a Chromium build.
//   node harness/screenshots.mjs            (uses the globally installed playwright)
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const globalRoot = execSync('npm root -g').toString().trim();
const { chromium } = require(join(globalRoot, 'playwright'));

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const PAGES = [
  [pathToFileURL(join(root, 'docs', 'index.html')).href, join(root, 'docs', 'img')],
  [pathToFileURL(join(root, 'docs', 'index.en.html')).href, join(root, 'docs', 'img', 'en')],
];

// Overview cards in page order: 0 cost, 1 cumulative, 2 budget, 3 metrics, 4 forecast,
// then the single-run view: 5 timeline, 6 weekly table.
const CARDS = { cost: 0, cumulative: 1, budget: 2, metrics: 3, forecast: 4, timeline: 5 };
const SHOTS = [
  ['real-header', 'real/real', 'header'],
  ['real-cost', 'real/real', 'cost'],
  ['real-cumulative', 'real/real', 'cumulative'],
  ['real-budget', 'real/real', 'budget'],
  ['real-metrics', 'real/real', 'metrics'],
  ['real-forecast', 'real/real', 'forecast'],
  ['real-timeline', 'real/real', 'timeline', '1'],
  ['sim-strong-header', 'sim/strong', 'header'],
  ['sim-strong-cost', 'sim/strong', 'cost'],
  ['sim-strong-cumulative', 'sim/strong', 'cumulative'],
  ['sim-weak-header', 'sim/weak', 'header'],
  ['sim-weak-cumulative', 'sim/weak', 'cumulative'],
];

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1100, height: 900 }, deviceScaleFactor: 1.5, colorScheme: 'light',
});
for (const [pageUrl, outDir] of PAGES) {
  mkdirSync(outDir, { recursive: true });
  for (const [name, ds, part, rep = 'all'] of SHOTS) {
    // The page reads its filters from the hash only on load, so force a fresh load.
    await page.goto('about:blank');
    await page.goto(`${pageUrl}#ds=${ds}&rep=${rep}`);
    // The sticky filter bar would overlay element screenshots taken below the fold.
    await page.addStyleTag({ content: '.filters { position: static !important; }' });
    const target = part === 'header'
      ? page.locator('header')
      : page.locator('section.card').nth(CARDS[part]);
    const path = join(outDir, `${name}.png`);
    await target.screenshot({ path });
    console.log(path.slice(root.length + 1));
  }
}
await browser.close();
