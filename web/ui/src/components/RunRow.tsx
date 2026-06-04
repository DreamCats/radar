import { formatTime } from "../lib/datetime";
import type { RunItem } from "../types";

export function RunRow({ run }: { run: RunItem }) {
  return (
    <article className="run-row">
      <div>
        <p className="run-title">{run.kind}</p>
        <p className="run-target">{run.target}</p>
      </div>
      <span className={`status ${run.status}`}>{run.status}</span>
      <span>{formatTime(run.started_at)}</span>
      <span>raw {run.raw_count}</span>
      <span>stored {run.stored_count}</span>
    </article>
  );
}
