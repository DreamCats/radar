import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { fetchRuns } from "../api/radarApi";
import { PanelTitle } from "../components/PanelTitle";
import { RunRow } from "../components/RunRow";
import type { RunItem } from "../types";

export function RunsPage() {
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      setRuns(await fetchRuns());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <section className="content-panel full">
      <PanelTitle title="最近运行" meta={`${runs.length} 条`}>
        <button className="icon-button" type="button" onClick={() => void refresh()} title="刷新">
          <RefreshCw size={16} />
          刷新
        </button>
      </PanelTitle>
      {error && <p className="error-line">{error}</p>}
      <div className="run-list">
        {runs.map((run) => (
          <RunRow key={run.run_id} run={run} />
        ))}
        {runs.length === 0 && <p className="empty-line">暂无运行记录</p>}
      </div>
    </section>
  );
}
