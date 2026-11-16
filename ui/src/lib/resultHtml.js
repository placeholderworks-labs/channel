const FONT_LINK_ID = "pw-result-fonts";
const FONT_HREF =
  "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Poppins:wght@400;500;600&display=swap";

const STRIP_TAGS = "script,iframe,object,embed,base,link,meta,form,noscript,template";
const EAGER_PHOTOS = 3;

const SAFE_URL = /^(https?:|mailto:|tel:|data:image\/|#|\/|\.\/|\.\.\/)/i;

const RESET = `
:host{display:block;color-scheme:light;background:#fff;color:#202020;
  font:400 14px/1.5 Poppins,Inter,system-ui,sans-serif}
:host *{box-sizing:border-box}
a:focus-visible,button:focus-visible{outline:2px solid #00558f;outline-offset:2px}
img{max-width:100%}
`;

const SUBJECTS = ["hotel", "flight", "train", "bus", "holiday", "cab", "booking"];

function labelFor(root) {
  const carousels = [...root.querySelectorAll('[class*="-carousel"]')];
  for (const node of carousels) {
    for (const name of node.classList) {
      const subject = name.replace(/-carousel$/, "");
      if (SUBJECTS.includes(subject)) return `${subject.toUpperCase()}S`;
    }
  }
  return "RESULTS";
}

const SIGNATURE_CHARS = 96;

export function signatureOf(html) {
  return String(html || "")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, SIGNATURE_CHARS);
}

export function prepareResult(raw) {
  const doc = new DOMParser().parseFromString(String(raw || ""), "text/html");
  const body = doc.body;
  if (!body) return null;

  let style = "";
  body.querySelectorAll("style").forEach((el) => {
    style += `${el.textContent}\n`;
    el.remove();
  });
  doc.head.querySelectorAll("style").forEach((el) => {
    style += `${el.textContent}\n`;
    el.remove();
  });
  style = style.replace(/@import[^;]*;/g, "");

  body.querySelectorAll(STRIP_TAGS).forEach((el) => el.remove());

  const label = labelFor(body);
  let imageCount = 0;
  let photoCount = 0;

  body.querySelectorAll("*").forEach((el) => {
    for (const attr of [...el.attributes]) {
      const name = attr.name.toLowerCase();
      if (name.startsWith("on")) {
        el.removeAttribute(attr.name);
        continue;
      }
      if ((name === "href" || name === "src") && !SAFE_URL.test(attr.value.trim())) {
        el.removeAttribute(attr.name);
      }
    }

    const tag = el.tagName.toLowerCase();
    if (tag === "a") {
      el.setAttribute("target", "_blank");
      el.setAttribute("rel", "noopener noreferrer");
    }
    if (tag === "img") {
      imageCount += 1;
      el.setAttribute("decoding", "async");
      el.setAttribute("referrerpolicy", "no-referrer");
      if ((el.getAttribute("src") || "").startsWith("http")) {
        photoCount += 1;
        el.setAttribute("loading", photoCount <= EAGER_PHOTOS ? "eager" : "lazy");
      }
    }
  });

  return { style, body: body.innerHTML, label, imageCount, photoCount };
}

export function hoistFonts() {
  if (document.getElementById(FONT_LINK_ID)) return;
  const link = document.createElement("link");
  link.id = FONT_LINK_ID;
  link.rel = "stylesheet";
  link.href = FONT_HREF;
  document.head.appendChild(link);
}

export function mountResult(host, prepared) {
  if (!host || !prepared) return;
  const root = host.shadowRoot || host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>${RESET}${prepared.style}</style>${prepared.body}`;

  root.querySelectorAll("img").forEach((img) => {
    img.addEventListener(
      "error",
      () => {
        img.style.visibility = "hidden";
      },
      { once: true }
    );
  });
}

function findScroller(root) {
  for (const el of root.querySelectorAll("*")) {
    if (el.scrollWidth - el.clientWidth < 24) continue;
    const overflow = getComputedStyle(el).overflowX;
    if (overflow === "auto" || overflow === "scroll") return el;
  }
  return null;
}

export function autoScrollCards(host) {
  const root = host && host.shadowRoot;
  if (!root) return () => {};

  const scroller = findScroller(root);
  if (!scroller) return () => {};

  scroller.style.scrollSnapType = "x mandatory";
  scroller.style.scrollPaddingLeft = "0px";
  scroller.style.overscrollBehaviorX = "contain";

  for (const card of scroller.children) {
    card.style.scrollSnapAlign = "start";
    card.style.scrollSnapStop = "always";
  }

  scroller.scrollLeft = 0;
  return () => {};
}
