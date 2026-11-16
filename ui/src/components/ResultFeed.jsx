import { useEffect, useRef } from "react";
import ResultBlock from "./ResultBlock";
import ResultSkeleton from "./ResultSkeleton";

export default function ResultFeed({ results, live, empty }) {
  const feedRef = useRef(null);
  const newest = results.length ? results[results.length - 1] : null;
  const newestKey = newest ? `${newest.seq}:${newest.status}` : "";

  useEffect(() => {
    const feed = feedRef.current;
    if (!feed || !newestKey) return;

    const seq = newestKey.split(":")[0];
    const smooth =
      !window.matchMedia || !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const pin = (behavior) => {
      const block = feed.querySelector(`[data-seq="${seq}"]`);
      if (!block) return;
      const target = Math.max(0, block.offsetTop - 12);
      if (behavior === "smooth" && typeof feed.scrollTo === "function") {
        feed.scrollTo({ top: target, behavior });
      } else {
        feed.scrollTop = target;
      }
    };

    pin(smooth ? "smooth" : "auto");
    const settle = setTimeout(() => pin("auto"), 700);
    return () => clearTimeout(settle);
  }, [newestKey]);

  return (
    <div className="result-feed" ref={feedRef}>
      {results.length === 0 ? (
        <div className="result-idle">{empty}</div>
      ) : (
        results.map((result) =>
          result.status === "ready" ? (
            <ResultBlock key={result.seq} result={result} />
          ) : (
            <ResultSkeleton
              key={result.seq}
              seq={result.seq}
              failed={result.status === "error"}
            />
          )
        )
      )}
      {!live && results.length > 0 && (
        <div className="result-idle tiny">Session ended. Results stay until you start again.</div>
      )}
    </div>
  );
}
