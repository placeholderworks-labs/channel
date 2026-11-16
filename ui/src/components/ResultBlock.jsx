import { useEffect, useMemo, useRef } from "react";
import { clockTime } from "../lib/format";
import { autoScrollCards, hoistFonts, mountResult, prepareResult } from "../lib/resultHtml";

export default function ResultBlock({ result }) {
  const hostRef = useRef(null);
  const prepared = useMemo(
    () => (result.html ? prepareResult(result.html) : null),
    [result.html]
  );

  useEffect(() => {
    if (!prepared) return;
    hoistFonts();
    mountResult(hostRef.current, prepared);
    return autoScrollCards(hostRef.current);
  }, [prepared]);

  return (
    <article className="result-block" data-seq={result.seq}>
      <header className="result-head">
        <span className="result-label">{prepared?.label || "RESULTS"}</span>
        <span className="tiny faint">{clockTime(result.at)}</span>
      </header>
      <div className="result-host" ref={hostRef} />
    </article>
  );
}
