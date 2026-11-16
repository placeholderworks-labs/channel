import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { mergeResult } from "../src/lib/results.js";
import { signatureOf } from "../src/lib/resultHtml.js";

let pass = 0;
let fail = 0;
const check = (name, fn) => {
  try {
    fn();
    console.log("  PASS  " + name);
    pass++;
  } catch (e) {
    console.log("  FAIL  " + name + " — " + e.message);
    fail++;
  }
};

const trains = (date = "25 Sep 2026", to = "C Shivaji Mah T", cards = 3) =>
  `<style>.a{}</style><div class="class-carousel"></div><div class="train-carousel">` +
  `<h3>Trains from New Delhi to ${to}</h3>` +
  `<p>${date} • 16 trains found • General Quota</p>` +
  Array.from({ length: cards }, (_, i) => `<div>Train ${i} 1290${i}</div>`).join("") +
  `</div>`;

console.log("\n1. the bug from the screenshot: the same listing twice");
check("two turns, same search → one block", () => {
  let list = [];
  list = mergeResult(list, 4, { status: "ready", html: trains() });
  list = mergeResult(list, 7, { status: "ready", html: trains(undefined, undefined, 1) });
  assert.equal(list.length, 1, `got ${list.length} blocks`);
  assert.equal(list[0].seq, 7, "the newest should win");
});

console.log("\n2. genuinely different searches still stack");
check("different date → two blocks", () => {
  let list = [];
  list = mergeResult(list, 1, { status: "ready", html: trains("25 Sep 2026") });
  list = mergeResult(list, 2, { status: "ready", html: trains("26 Sep 2026") });
  assert.equal(list.length, 2);
});
check("different destination → two blocks", () => {
  let list = [];
  list = mergeResult(list, 1, { status: "ready", html: trains(undefined, "C Shivaji Mah T") });
  list = mergeResult(list, 2, { status: "ready", html: trains(undefined, "Mumbai Central") });
  assert.equal(list.length, 2);
});

console.log("\n3. the stale error box");
check("a listing clears an earlier failure", () => {
  let list = [];
  list = mergeResult(list, 1, { status: "error" });
  list = mergeResult(list, 2, { status: "ready", html: trains() });
  assert.equal(list.length, 1);
  assert.equal(list[0].status, "ready");
});
check("two failures do not stack", () => {
  let list = [];
  list = mergeResult(list, 1, { status: "error" });
  list = mergeResult(list, 2, { status: "error" });
  assert.equal(list.length, 1);
});

console.log("\n4. the rest of the feed still behaves");
check("a pending row upgrades in place", () => {
  let list = [];
  list = mergeResult(list, 1, { status: "pending" });
  list = mergeResult(list, 1, { status: "ready", html: trains() });
  assert.equal(list.length, 1);
  assert.equal(list[0].status, "ready");
});
check("null drops the row", () => {
  const list = mergeResult([], 1, { status: "pending" });
  assert.equal(mergeResult(list, 1, null).length, 0);
});
check("the feed is capped at four", () => {
  let list = [];
  for (let i = 1; i <= 8; i++) {
    list = mergeResult(list, i, { status: "ready", html: trains(`${i} Sep 2026`) });
  }
  assert.equal(list.length, 4);
  assert.equal(list[3].seq, 8);
});

console.log("\n5. the server's result id beats the text heuristic");
check("same id, completely different markup → one block", () => {
  let list = [];
  list = mergeResult(list, 1, { status: "ready", html: trains(), resultId: "search_trains:abc" });
  list = mergeResult(list, 2, {
    status: "ready",
    html: "<div class='train-carousel'><h3>Totally re-rendered</h3></div>",
    resultId: "search_trains:abc",
  });
  assert.equal(list.length, 1, "an id means the same listing however it renders");
  assert.equal(list[0].seq, 2);
});
check("different id, near-identical markup → two blocks", () => {
  let list = [];
  list = mergeResult(list, 1, { status: "ready", html: trains(), resultId: "search_trains:aaa" });
  list = mergeResult(list, 2, { status: "ready", html: trains(), resultId: "search_trains:bbb" });
  assert.equal(list.length, 2, "the text heuristic would have collapsed these");
});
check("no id falls back to the text signature", () => {
  let list = [];
  list = mergeResult(list, 1, { status: "ready", html: trains() });
  list = mergeResult(list, 2, { status: "ready", html: trains(undefined, undefined, 1) });
  assert.equal(list.length, 1);
});
check("a filtered view carries no id, so it does not replace the listing", () => {
  let list = [];
  list = mergeResult(list, 1, { status: "ready", html: trains(), resultId: "search_trains:abc" });
  list = mergeResult(list, 2, {
    status: "ready",
    html: "<div class='train-carousel'><h3>Cheapest only</h3></div>",
    resultId: "",
  });
  assert.equal(list.length, 2);
});

console.log("\n6. the signature is text, not markup");
check("tags and styles are stripped", () => {
  const sig = signatureOf(trains());
  assert.ok(sig.startsWith("Trains from New Delhi"), sig);
  assert.ok(!sig.includes("<"), "tags should be stripped");
  assert.ok(!sig.includes(".a{}"), "style block should be stripped");
});

console.log("\n7. the results feed cannot compress what it holds");
check("the feed stacks with flex, not grid", () => {
  const css = readFileSync(new URL("../src/styles/app.css", import.meta.url), "utf8");
  const rule = css.match(/\.result-feed\s*\{([^}]*)\}/);
  assert.ok(rule, ".result-feed rule not found");
  assert.match(rule[1], /display:\s*flex/, "the feed must be a flex column");
  assert.ok(!/display:\s*grid/.test(rule[1]), "a grid feed compresses its rows");
  assert.match(css, /\.result-feed\s*>\s*\*\s*\{[^}]*flex:\s*none/,
    "every child must be pinned with flex:none");
});

console.log("\n8. the docs page navigates to sections that exist");
function docsNav() {
  const src = readFileSync(new URL("../src/pages/Docs.jsx", import.meta.url), "utf8");
  const parts = src.slice(src.indexOf("const PARTS = ["), src.indexOf("const SECTIONS ="));
  const subs = [...parts.matchAll(/\{ id: "([^"]+)", label: "[^"]*" \}/g)].map((m) => m[1]);
  const all = [...parts.matchAll(/id:\s*"([^"]+)"/g)].map((m) => m[1]);
  return {
    src,
    subs,
    sections: all.filter((id) => !subs.includes(id)),
    declared: all,
    groups: [...parts.matchAll(/part:\s*"([^"]+)"/g)].map((m) => m[1]),
  };
}

check("every nav entry and every heading line up", () => {
  const { src, sections, subs, declared } = docsNav();
  const rendered = {
    sections: [...src.matchAll(/<Section\s+id="([^"]+)"/g)].map((m) => m[1]),
    subs: [...src.matchAll(/<Sub id="([^"]+)">/g)].map((m) => m[1]),
  };

  for (const [kind, nav, dom] of [
    ["section", sections, rendered.sections],
    ["subsection", subs, rendered.subs],
  ]) {
    const orphanNav = nav.filter((id) => !dom.includes(id));
    const unreachable = dom.filter((id) => !nav.includes(id));
    assert.deepEqual(orphanNav, [], `nav points at missing ${kind}s: ${orphanNav}`);
    assert.deepEqual(unreachable, [], `${kind}s with no nav entry: ${unreachable}`);
  }
  assert.equal(new Set(declared).size, declared.length, "an id is listed twice");
});

check("headings appear in the order the nav lists them", () => {
  const { src, declared } = docsNav();
  const order = [...src.matchAll(/<(?:Section\s+id|Sub id)="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, declared, "document order does not match nav order");
});

check("the page is organised into its nine parts", () => {
  const { groups } = docsNav();
  assert.deepEqual(
    groups,
    [
      "Overview",
      "High level design",
      "Low level design",
      "Speech to text",
      "The language model",
      "Text to speech",
      "Telephony",
      "Walkthroughs",
      "Operations",
    ],
    groups.join(", ")
  );
});

check("the docs carry no em dashes or double hyphens", () => {
  for (const file of ["../src/pages/Docs.jsx", "../src/docs/diagrams.jsx"]) {
    const text = readFileSync(new URL(file, import.meta.url), "utf8");
    const prose = text.replace(/var\(--[a-z-]+\)/g, "").replace(/"--[a-z]+"/g, "");
    assert.ok(!/[\u2013\u2014]/.test(prose), `${file} contains an en or em dash`);
    assert.ok(!/--/.test(prose), `${file} contains a double hyphen`);
  }
});

console.log(`\n${"=".repeat(50)}\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
