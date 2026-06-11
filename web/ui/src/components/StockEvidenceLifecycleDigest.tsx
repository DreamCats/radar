import type { StockEvidenceChainItem } from "../types";
import { Route } from "lucide-react";

export function StockEvidenceLifecycleDigest({ item }: { item: StockEvidenceChainItem }) {
  const digest = item.lifecycle_digest;
  if (!digest) {
    return (
      <section className="stock-evidence-card stock-evidence-card-lifecycle stock-evidence-lifecycle">
        <LifecycleHead />
        <p className="stock-evidence-empty">尚未生成。可在作业中心运行「机会生命周期摘要」。</p>
      </section>
    );
  }
  return (
    <section className="stock-evidence-card stock-evidence-card-lifecycle stock-evidence-lifecycle">
      <LifecycleHead />
      <p>{digest.one_line || "暂无一句话摘要。"}</p>
      <DigestSection title="生命周期路径" items={digest.timeline} />
      <DigestSection title="阶段依据" items={digest.stage_reason} />
      <DigestSection title="缺口 / 反证" items={digest.missing_evidence} />
      <DigestSection title="后续观察" items={digest.next_watch} />
    </section>
  );
}

function LifecycleHead() {
  return (
    <div className="stock-evidence-card-head">
      <span>
        <Route size={15} />
      </span>
      <div>
        <strong>机会生命周期</strong>
        <small>把前面的证据串成一条可复盘路径。</small>
      </div>
    </div>
  );
}

function DigestSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="stock-evidence-section">
      <div className="stock-evidence-section-title">{title}</div>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="stock-evidence-empty">暂无。</p>
      )}
    </section>
  );
}
