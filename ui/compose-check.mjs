import { chromium } from "playwright";
const OUT = "/private/tmp/claude-501/-Users-happyyadav-Desktop-main-pipecat-v2v/74d45741-7f34-46b1-b48c-d09a8ecc2e95/scratchpad/shots";
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1440, height: 950 }, deviceScaleFactor: 2 })).newPage();
const errs = [];
p.on("pageerror", (e) => errs.push(e.message));
p.on("console", (m) => m.type() === "error" && errs.push(m.text()));

await p.goto("http://127.0.0.1:8410/dashboard", { waitUntil: "networkidle" });
await p.fill("#email", "happy.yadav@placeholderworks.com");
await p.fill("#password", "voicebot-dev");
await p.click('button[type="submit"]');
await p.waitForSelector(".chain");
console.log("signed in; store =", await p.locator(".sidebar-foot .pill").first().innerText());

await p.click('a[href="/dashboard/configuration"]');
await p.waitForSelector(".setrow");
await p.fill(".searchinput", "output gain");
await p.waitForTimeout(400);
await p.locator("#BOT_OUTPUT_GAIN_DB").fill("4.5");
await p.click(".actionbar .btn-primary");
await p.waitForSelector(".toast.ok", { timeout: 10000 });
console.log("save:", (await p.locator(".toast").first().innerText()).replace(/\n/g, " "));

await p.click('a[href="/dashboard/logs"]');
await p.waitForSelector(".logview");
await p.waitForTimeout(2500);
const pills = await p.locator(".page-head-row .pill").allInnerTexts();
console.log("logs pills:", pills.map((t) => t.replace(/\n/g, " ")).join(" | "));
console.log("log lines rendered:", await p.locator(".logline").count());
await p.screenshot({ path: `${OUT}/50-compose-logs.png` });

await p.click('a[href="/dashboard"]');
await p.waitForSelector(".chain");
await p.waitForTimeout(600);
await p.screenshot({ path: `${OUT}/51-compose-overview.png`, fullPage: true });

await b.close();
console.log(errs.length ? "ERRORS:\n" + errs.join("\n") : "no console errors");
