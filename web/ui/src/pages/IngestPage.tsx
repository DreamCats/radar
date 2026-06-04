import { useState } from "react";
import { Play } from "lucide-react";

import { ingestWechat } from "../api/radarApi";
import { DateField, SelectField } from "../components/FormFields";
import { PanelTitle } from "../components/PanelTitle";
import { toIso } from "../lib/datetime";
import type { IngestResultItem, IngestSource } from "../types";

export function IngestPage() {
  const [source, setSource] = useState<IngestSource>("all");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [force, setForce] = useState(false);
  const [result, setResult] = useState<IngestResultItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    setError(null);
    try {
      const items = await ingestWechat({
        source,
        start_time: toIso(start),
        end_time: toIso(end),
        force,
        chunk_hours: 1,
        concurrency: 4,
      });
      setResult(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "拉取失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="content-panel full narrow">
      <PanelTitle title="手动拉取" meta="同步触发" />
      <div className="ingest-form">
        <SelectField
          label="来源"
          value={source}
          onChange={(value) => setSource(value as IngestSource)}
          options={[
            ["all", "全部"],
            ["personal_message", "个人消息"],
            ["group_message", "个人群"],
          ]}
        />
        <DateField label="开始" value={start} onChange={setStart} />
        <DateField label="结束" value={end} onChange={setEnd} />
        <label className="check-field">
          <input checked={force} type="checkbox" onChange={(event) => setForce(event.target.checked)} />
          强制重拉
        </label>
        <button className="primary-button" type="button" disabled={loading || !start || !end} onClick={submit}>
          <Play size={16} />
          开始
        </button>
      </div>
      {error && <p className="error-line">{error}</p>}
      <div className="run-list">
        {result.map((item) => (
          <p className="result-line" key={`${item.source_key}-${item.run_id}`}>
            {item.source}: chunks={item.chunk_count} skipped={item.skipped_count} raw={item.raw_count}
            filtered={item.filtered_count} stored={item.stored_count} run_id={item.run_id}
          </p>
        ))}
      </div>
    </section>
  );
}
