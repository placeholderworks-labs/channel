import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";

const BUILT_IN = ["language_rule", "script_rule", "style_directive_rule", "expressive_tags_rule", "today", "timezone", "call_details"];
const TOKEN = /(\{[a-z][a-z0-9_]*\})/g;

function Highlights({ text, known }) {
  const parts = (text || "").split(TOKEN);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <mark key={i} className={known.has(part.slice(1, -1)) ? "vt-ok" : "vt-bad"}>{part}</mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
      {"\u200b"}
    </>
  );
}

const MIRRORED = [
  "boxSizing", "width", "height", "overflowX", "overflowY", "borderTopWidth", "borderRightWidth",
  "borderBottomWidth", "borderLeftWidth", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
  "fontStyle", "fontVariant", "fontWeight", "fontStretch", "fontSize", "lineHeight", "fontFamily",
  "textAlign", "textTransform", "textIndent", "letterSpacing", "wordSpacing", "tabSize", "whiteSpace", "wordBreak",
];

function caretPoint(el, position) {
  const div = document.createElement("div");
  const style = getComputedStyle(el);
  for (const prop of MIRRORED) div.style[prop] = style[prop];
  div.style.position = "absolute";
  div.style.visibility = "hidden";
  div.style.whiteSpace = "pre-wrap";
  div.style.wordWrap = "break-word";
  div.textContent = el.value.slice(0, position);
  const marker = document.createElement("span");
  marker.textContent = el.value.slice(position) || ".";
  div.appendChild(marker);
  document.body.appendChild(div);
  const point = {
    top: marker.offsetTop - el.scrollTop + parseFloat(style.lineHeight || 18),
    left: Math.min(marker.offsetLeft - el.scrollLeft, el.clientWidth - 240),
  };
  document.body.removeChild(div);
  return point;
}

const VarTextarea = forwardRef(function VarTextarea({ value, onChange, items = [], className = "", ...rest }, outer) {
  const ref = useRef(null);
  const backRef = useRef(null);
  const listRef = useRef(null);
  const [menu, setMenu] = useState(null);
  const caretAfter = useRef(null);
  useImperativeHandle(outer, () => ref.current);

  useLayoutEffect(() => {
    const el = ref.current;
    if (el && caretAfter.current !== null) {
      el.focus();
      el.selectionStart = el.selectionEnd = caretAfter.current;
      caretAfter.current = null;
    }
  }, [value]);

  const matches = menu
    ? items
        .filter((i) => i.key.includes(menu.query))
        .sort((a, b) => (b.key.startsWith(menu.query) ? 1 : 0) - (a.key.startsWith(menu.query) ? 1 : 0))
    : [];

  const refresh = (el) => {
    const caret = el.selectionStart;
    const before = el.value.slice(0, caret);
    const m = before.match(/\{([a-z0-9_]*)$/);
    if (!m || !items.length) return setMenu(null);
    setMenu({ query: m[1], start: caret - m[1].length - 1, end: caret, active: 0, ...caretPoint(el, caret) });
  };

  const pick = (item) => {
    const el = ref.current;
    if (!el || !menu) return;
    let end = menu.end;
    if (value[end] === "}") end += 1;
    const token = `{${item.key}}`;
    caretAfter.current = menu.start + token.length;
    onChange(value.slice(0, menu.start) + token + value.slice(end));
    setMenu(null);
  };

  const onKeyDown = (e) => {
    if (!menu || !matches.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      setMenu((m) => ({ ...m, active: (m.active + step + matches.length) % matches.length }));
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      pick(matches[Math.min(menu.active, matches.length - 1)]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setMenu(null);
    }
  };

  useLayoutEffect(() => {
    listRef.current?.querySelector(".vmenu-item.on")?.scrollIntoView({ block: "nearest" });
  }, [menu?.active]);

  useLayoutEffect(() => {
    const el = ref.current;
    const back = backRef.current;
    if (!el || !back) return undefined;
    const sync = () => {
      const style = getComputedStyle(el);
      for (const prop of MIRRORED) back.style[prop] = style[prop];
      back.style.width = `${el.offsetWidth}px`;
      back.style.height = `${el.offsetHeight}px`;
      back.style.whiteSpace = "pre-wrap";
      back.style.overflowWrap = "break-word";
      back.scrollTop = el.scrollTop;
    };
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const known = new Set([...BUILT_IN, ...items.map((i) => i.key)]);

  return (
    <div className="vta">
      <div ref={backRef} className="vta-back" aria-hidden="true">
        <Highlights text={value} known={known} />
      </div>
      <textarea
        ref={ref}
        className={className}
        value={value}
        onChange={(e) => { onChange(e.target.value); refresh(e.target); }}
        onKeyDown={onKeyDown}
        onClick={(e) => refresh(e.target)}
        onKeyUp={(e) => ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key) && refresh(e.target)}
        onBlur={() => setTimeout(() => setMenu(null), 150)}
        onScroll={(e) => {
          if (backRef.current) backRef.current.scrollTop = e.target.scrollTop;
          if (menu) refresh(ref.current);
        }}
        spellCheck={false}
        {...rest}
      />
      {menu && (
        <div ref={listRef} className="vmenu" role="listbox" style={{ top: menu.top, left: Math.max(menu.left, 0) }}>
          {matches.length === 0 ? (
            <div className="vmenu-empty">No variable starts with “{menu.query}”. Add it on the Variables tab</div>
          ) : (
            matches.map((item, i) => (
              <button
                type="button"
                key={item.key}
                role="option"
                aria-selected={i === menu.active}
                className={`vmenu-item ${i === menu.active ? "on" : ""}`}
                onMouseDown={(e) => { e.preventDefault(); pick(item); }}
                onMouseEnter={() => setMenu((m) => ({ ...m, active: i }))}
              >
                <span className="vmenu-key">{`{${item.key}}`}</span>
                <span className="vmenu-detail">{item.detail}</span>
                {item.group && <span className="vmenu-group">{item.group}</span>}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
});

export default VarTextarea;
