type LoadingVariant = "dashboard" | "strategy" | "organize";

export function PageLoadingState(props: { label: string; variant: LoadingVariant }) {
  const chartCount = props.variant === "dashboard" ? 7 : props.variant === "organize" ? 4 : 3;
  return (
    <div className={`page-loading-state page-loading-${props.variant}`} role="status" aria-live="polite">
      <LoadingPill label={props.label} />
      <div className="page-loading-metrics" aria-hidden="true">
        {Array.from({ length: 4 }).map((_, index) => (
          <span className="page-loading-metric" key={index}>
            <i />
            <b />
            <em />
          </span>
        ))}
      </div>
      <div className="page-loading-panels" aria-hidden="true">
        {Array.from({ length: chartCount }).map((_, index) => (
          <span className="page-loading-panel" key={index}>
            <i />
            <b />
            <em />
          </span>
        ))}
      </div>
    </div>
  );
}

export function PageRefreshProgress(props: { label: string }) {
  return (
    <div className="page-refresh-progress" role="status" aria-live="polite">
      <LoadingPill label={props.label} />
      <span className="page-refresh-bar" aria-hidden="true" />
    </div>
  );
}

function LoadingPill(props: { label: string }) {
  return (
    <span className="page-loading-pill">
      <i aria-hidden="true" />
      {props.label}
    </span>
  );
}
