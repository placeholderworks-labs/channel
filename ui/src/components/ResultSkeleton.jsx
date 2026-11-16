export default function ResultSkeleton({ seq, failed = false }) {
  if (failed) {
    return (
      <article className="result-block result-block-flat" data-seq={seq}>
        <div className="result-note">
          Results didn't come through. Ask again and I'll pull them up.
        </div>
      </article>
    );
  }

  return (
    <article className="result-block result-block-flat" data-seq={seq}>
      <header className="result-head">
        <span className="result-label">Searching…</span>
      </header>
      <div className="result-skel" role="status" aria-live="polite" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div className="skel-card" key={i}>
            <div className="skel-img" />
            <div className="skel-line" />
            <div className="skel-line short" />
          </div>
        ))}
      </div>
    </article>
  );
}
