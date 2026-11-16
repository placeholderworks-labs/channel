import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");

let chromium;
try {
  ({ chromium } = await import("playwright-core"));
} catch {
  console.log("\nlayout: skipped — playwright-core is not installed");
  process.exit(0);
}

const PASS = [];
const FAIL = [];
const check = (name, cond, detail = "") => {
  (cond ? PASS : FAIL).push(name);
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
};

const css = fs.readFileSync(path.join(root, "src/styles/app.css"), "utf8");

const block = '<article class="result-block"><div style="height:500px">result</div></article>';

let browser;
try {
  browser = await chromium.launch({ channel: "chrome" });
} catch (e) {
  console.log(`\nlayout: skipped — no browser available (${e.message.split("\n")[0]})`);
  process.exit(0);
}

const page = await browser.newPage({ viewport: { width: 1470, height: 960 } });

async function feedWith(count) {
  await page.setContent(`<!doctype html><html><head><style>${css}</style></head><body>
    <div class="rtc-layout"><div class="rtc-main">
      <section class="card play-card">
        <div class="result-feed" id="feed">${block.repeat(count)}</div>
        <div class="micbar">mic</div>
      </section>
    </div><aside class="rtc-side"><section class="card">side</section></aside></div>
  </body></html>`);
  return page.evaluate(() => {
    const feed = document.getElementById("feed");
    const blocks = [...feed.querySelectorAll(".result-block")];
    return {
      feedH: Math.round(feed.getBoundingClientRect().height),
      feedScrollH: feed.scrollHeight,
      heights: blocks.map((b) => Math.round(b.getBoundingClientRect().height)),
      lost: blocks.map((b) => b.scrollHeight - b.clientHeight),
    };
  });
}

console.log("\n1. one result is never compressed");
let r = await feedWith(1);
check("it keeps its full height", r.heights[0] === 500, `${r.heights[0]}px of 500`);

console.log("\n2. results past the fold are not squeezed to fit — the feed scrolls instead");
for (const count of [2, 3, 5]) {
  r = await feedWith(count);
  const short = r.heights.filter((h) => h < 500);
  check(
    `  ${count} results all keep their height`,
    short.length === 0,
    short.length ? `${short.length} compressed to ${short.join(", ")}px` : "",
  );
  check(
    `  ${count} results: nothing is clipped`,
    r.lost.every((l) => l <= 0),
    r.lost.some((l) => l > 0) ? `lost ${r.lost.join(", ")}px` : "",
  );
}

console.log("\n3. the feed stays bounded and scrollable");
r = await feedWith(5);
check("the feed itself does not grow past its cap", r.feedH <= 640, `${r.feedH}px`);
check(
  "and the overflow is reachable by scrolling",
  r.feedScrollH > r.feedH,
  `scrollH ${r.feedScrollH} vs ${r.feedH}`,
);

await browser.close();

console.log(`\n${"=".repeat(50)}\n${PASS.length} passed, ${FAIL.length} failed`);
if (FAIL.length) {
  console.log("FAILED: " + FAIL.join(", "));
  process.exit(1);
}
