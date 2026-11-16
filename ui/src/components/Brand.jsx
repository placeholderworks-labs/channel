const FACETS = [
  ["268,425 428,227 428,425", "#83022e"],
  ["428,227 628,425 428,425", "#ad0a40"],
  ["428,227 682,227 878,425 628,425", "#ee0f52"],
  ["682,227 900,227 1043,371 990,425 878,425", "#f9286b"],
  ["428,425 628,425 628,618 428,618", "#f61d61"],
  ["628,425 990,425 810,618", "#ad0a40"],
  ["628,425 810,618 628,618", "#83022e"],
  ["268,425 428,425 428,808 268,808", "#b1023f"],
  ["428,618 628,618 428,808", "#8c0130"],
  ["268,808 438,808 268,987", "#ea0c50"],
];

export function Mark({ size = 28, title = "PlaceholderWorks", className = "" }) {
  return (
    <svg
      className={`pw-mark ${className}`}
      width={size}
      height={size}
      viewBox="248 207 815 800"
      role="img"
      aria-label={title}
    >
      {FACETS.map(([points, fill]) => (
        <polygon key={points} points={points} fill={fill} />
      ))}
    </svg>
  );
}

function Bracket({ flip = false }) {
  return (
    <svg className="pw-bracket" viewBox="0 0 24 64" aria-hidden="true" style={flip ? { transform: "scaleX(-1)" } : undefined}>
      <polygon points="7,0 24,0 24,9 15,9 15,55 24,55 24,64 7,64 0,57 0,7" fill="#ee0f52" />
      <polygon points="0,7 7,0 15,9 15,20 0,20" fill="#b1023f" />
      <polygon points="0,44 15,44 15,55 7,64 0,57" fill="#f9286b" />
    </svg>
  );
}

export function Wordmark({ className = "" }) {
  return (
    <span className={`pw-wordmark ${className}`} aria-label="PlaceholderWorks" role="img">
      <Bracket />
      <span className="pw-wordmark-text" aria-hidden="true">placeholderworks</span>
      <Bracket flip />
    </span>
  );
}

export function Facets({ className = "" }) {
  return (
    <svg className={`pw-facets ${className}`} viewBox="248 207 815 800" aria-hidden="true">
      {FACETS.map(([points, fill], i) => (
        <polygon key={points} points={points} fill={fill} style={{ animationDelay: `${i * 0.06}s` }} />
      ))}
    </svg>
  );
}
