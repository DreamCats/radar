import type { ReactNode } from "react";
import { Gauge, ShieldAlert, TrendingUp, Users } from "lucide-react";

import type {
  StrategyOpportunity,
  StrategyRelatedStock,
  StrategySourceSignal,
  StrategyStockCandidate,
} from "../types";
import { ChatLauncher } from "./ChatLauncher";

export function OpportunityCard({
  item,
  onStockOpen,
}: {
  item: StrategyOpportunity;
  onStockOpen: (stock: StrategyRelatedStock) => void;
}) {
  const topStocks = item.related_stocks.slice(0, 4);
  const sources = item.top_sources.slice(0, 3);
  return (
    <article className="strategy-opportunity-card">
      <div className="strategy-opportunity-head">
        <div>
          <span className={levelClass(item.attention_level)}>{item.attention_level}</span>
          <h2>{item.name}</h2>
        </div>
        <div className="strategy-score">
          <strong>{item.score.toFixed(0)}</strong>
          <span>机会分</span>
        </div>
      </div>
      <p className="strategy-reason">{item.reason}</p>
      <div className="strategy-signal-grid">
        <Signal label="拐点" value={`${item.acceleration.toFixed(1)}x`} icon={<TrendingUp size={15} />} />
        <Signal label="广度" value={`${item.sender_count}人/${item.group_count}群`} icon={<Users size={15} />} />
        <Signal
          label="全量T+5"
          value={formatPercent(item.opportunity_backtest.average_excess_return_t5, true)}
          icon={<Gauge size={15} />}
          tone={item.opportunity_backtest.average_excess_return_t5}
        />
        <Signal label="风险" value={`${item.risk_count}条`} icon={<ShieldAlert size={15} />} />
      </div>
      <div className="strategy-backtest-strip">
        <BacktestMetric label="全量机会" metric={item.opportunity_backtest} />
        <BacktestMetric label="精选股票" metric={item.selected_stock_backtest} />
      </div>
      <div className="strategy-tag-row">
        {item.catalyst_terms.slice(0, 5).map((term) => (
          <span className="strategy-chip positive" key={term}>
            {term}
          </span>
        ))}
        {item.risk_terms.slice(0, 3).map((term) => (
          <span className="strategy-chip risk" key={term}>
            {term}
          </span>
        ))}
      </div>
      <p className="strategy-risk">{item.risk_summary}</p>
      {topStocks.length > 0 && (
        <div className="strategy-card-section">
          <span className="strategy-section-label">相关股票</span>
          <div className="strategy-stock-strip">
            {topStocks.map((stock) => (
              <button className="strategy-stock-pill strategy-stock-button" type="button" key={stock.ts_code} onClick={() => onStockOpen(stock)}>
                <div>
                  <strong>{stock.stock_name}</strong>
                  <span className={decisionClass(stock.decision_bucket)}>{stock.decision_bucket}</span>
                  {stock.lifecycle_state && (
                    <span className={`strategy-stock-state strategy-stock-state-${stock.lifecycle_state}`}>
                      {stock.lifecycle_state}
                    </span>
                  )}
                  {stock.lifecycle_state === "发酵中" && stock.price_position && (
                    <span className={`strategy-price-position strategy-price-position-${stock.price_position}`}>
                      {stock.price_position}
                    </span>
                  )}
                  {stock.event_credibility && (
                    <span className={credibilityClass(stock.event_credibility.level)}>
                      {stock.event_credibility.level}
                    </span>
                  )}
                </div>
                <em className={returnToneClass(stock.average_excess_return_t5)}>
                  实时 {stock.realtime_score.toFixed(0)} · T+5 {formatPercent(stock.average_excess_return_t5, true)}
                </em>
                <small className={returnToneClass(stock.price_return_since_first_seen)}>
                  首现后 {formatPercent(stock.price_return_since_first_seen, true)}
                  {stock.signal_age_days !== undefined && stock.signal_age_days !== null ? ` · ${stock.signal_age_days}天` : ""}
                </small>
                {stock.event_credibility?.first_source_name && (
                  <small>
                    首提 {stock.event_credibility.first_source_name}
                    {stock.event_credibility.risks[0] ? ` · ${stock.event_credibility.risks[0]}` : ""}
                  </small>
                )}
                {stock.decision_reason && <small>{stock.decision_reason}</small>}
                {stock.lifecycle_reason && <small>{stock.lifecycle_reason}</small>}
              </button>
            ))}
          </div>
        </div>
      )}
      {sources.length > 0 && (
        <div className="strategy-card-section">
          <span className="strategy-section-label">主要来源</span>
          <div className="strategy-source-strip">
            {sources.map((source) => (
              <span key={source.name}>{source.name}</span>
            ))}
          </div>
        </div>
      )}
      <div className="chat-card-action-row">
        <ChatLauncher
          title={item.name}
          subtitle={item.reason}
          surface="发酵确认"
          entityId={item.key}
          buttonLabel="解释机会"
          buttonClassName="btn btn-sm chat-inline-action"
          context={[
            { label: "关注级别", value: item.attention_level },
            { label: "机会分", value: item.score.toFixed(0) },
            { label: "拐点", value: `${item.acceleration.toFixed(1)}x` },
            { label: "广度", value: `${item.sender_count}人/${item.group_count}群` },
            { label: "风险", value: `${item.risk_count}条` },
            { label: "全量T+5", value: formatPercent(item.opportunity_backtest.average_excess_return_t5, true) },
            { label: "精选T+5", value: formatPercent(item.selected_stock_backtest.average_excess_return_t5, true) },
            { label: "相关股票", value: topStocks.map((stock) => stock.stock_name).join(" / ") || "-" },
          ]}
          evidence={[
            item.reason,
            item.risk_summary,
            item.catalyst_terms.length ? `催化：${item.catalyst_terms.slice(0, 5).join(" / ")}` : "",
            item.risk_terms.length ? `风险：${item.risk_terms.slice(0, 5).join(" / ")}` : "",
            sources.length ? `主要来源：${sources.map((source) => source.name).join(" / ")}` : "",
          ].filter((line) => line)}
          suggestedQuestions={[
            "这条机会的核心催化、反证和当前可操作性是什么？",
            "相关股票里哪些更值得优先深挖？为什么？",
            "请基于来源质量和 T+5 回测判断这个主题是否过热。",
          ]}
        />
      </div>
    </article>
  );
}

export function SourceRow({ item }: { item: StrategySourceSignal }) {
  return (
    <article className="strategy-compact-row">
      <strong>{item.name}</strong>
      <span>{item.event_count} 事件</span>
      <em className={returnToneClass(item.average_excess_return_t5)}>{formatPercent(item.average_excess_return_t5, true)}</em>
    </article>
  );
}

export function DecisionStockGroup({
  group,
  onStockOpen,
}: {
  group: StockDecisionGroup;
  onStockOpen: (stock: StrategyStockCandidate) => void;
}) {
  return (
    <section className="strategy-stock-group">
      <div className="strategy-stock-group-head">
        <strong>{group.bucket}</strong>
        <span>
          {group.items.length} 个 · {group.meta}
        </span>
      </div>
      {group.items.length ? (
        <div className="strategy-compact-list">
          {group.items.map((item) => (
            <StockRow item={item} key={item.ts_code} onStockOpen={onStockOpen} />
          ))}
        </div>
      ) : (
        <p className="strategy-stock-group-empty">暂无</p>
      )}
    </section>
  );
}

export type StockDecisionGroup = {
  bucket: StrategyStockCandidate["decision_bucket"];
  meta: string;
  items: StrategyStockCandidate[];
};

export function groupStocksByDecision(stocks: StrategyStockCandidate[]): StockDecisionGroup[] {
  return [
    {
      bucket: "今日可关注",
      meta: "发酵中/初现，位置未过热",
      items: stocks.filter((item) => item.decision_bucket === "今日可关注"),
    },
    {
      bucket: "观察等待",
      meta: "逻辑或价格还需确认",
      items: stocks.filter((item) => item.decision_bucket === "观察等待"),
    },
    {
      bucket: "已兑现复盘",
      meta: "不追高，用来验证来源",
      items: stocks.filter((item) => item.decision_bucket === "已兑现复盘"),
    },
  ];
}

function StockRow({ item, onStockOpen }: { item: StrategyStockCandidate; onStockOpen: (stock: StrategyStockCandidate) => void }) {
  return (
    <button className="strategy-compact-row stock strategy-stock-row-button" type="button" onClick={() => onStockOpen(item)}>
      <div className="strategy-compact-main">
        <strong>{item.stock_name}</strong>
        <span className={decisionClass(item.decision_bucket)}>{item.decision_bucket}</span>
        {item.lifecycle_state && (
          <span className={`strategy-stock-state strategy-stock-state-${item.lifecycle_state}`}>
            {item.lifecycle_state}
          </span>
        )}
        {item.lifecycle_state === "发酵中" && item.price_position && (
          <span className={`strategy-price-position strategy-price-position-${item.price_position}`}>
            {item.price_position}
          </span>
        )}
        {item.event_credibility && (
          <span className={credibilityClass(item.event_credibility.level)}>{item.event_credibility.level}</span>
        )}
      </div>
      <span>
        实时 {item.realtime_score.toFixed(0)} · {item.source_count} 来源 · {item.event_count} 事件
      </span>
      <em className={returnToneClass(item.average_excess_return_t5)}>T+5 {formatPercent(item.average_excess_return_t5, true)}</em>
      {item.event_credibility?.first_source_name && (
        <small>
          首提 {item.event_credibility.first_source_name}
          {item.event_credibility.reasons[0] ? ` · ${item.event_credibility.reasons[0]}` : ""}
        </small>
      )}
      {item.decision_reason && <small>{item.decision_reason}</small>}
      {item.lifecycle_reason && <small>{item.lifecycle_reason}</small>}
    </button>
  );
}

function BacktestMetric(props: { label: string; metric: StrategyOpportunity["opportunity_backtest"] }) {
  return (
    <div className="strategy-backtest-metric">
      <span>{props.label}</span>
      <strong className={returnToneClass(props.metric.average_excess_return_t5)}>
        {formatPercent(props.metric.average_excess_return_t5, true)}
      </strong>
      <em>
        T+5 {formatPercent(props.metric.win_rate_t5)} · 成熟 {props.metric.matured_event_count}/{props.metric.event_count}
        {props.metric.pending_event_count > 0 ? ` · 待 ${props.metric.pending_event_count}` : ""}
      </em>
    </div>
  );
}

function Signal(props: { label: string; value: string; icon: ReactNode; tone?: number | null }) {
  return (
    <div className="strategy-signal">
      <span>
        {props.icon}
        {props.label}
      </span>
      <strong className={props.tone !== undefined ? returnToneClass(props.tone) : ""}>{props.value}</strong>
    </div>
  );
}

function levelClass(level: StrategyOpportunity["attention_level"]): string {
  return `strategy-level strategy-level-${level}`;
}

function credibilityClass(level: NonNullable<StrategyRelatedStock["event_credibility"]>["level"]): string {
  return `strategy-credibility strategy-credibility-${level}`;
}

function decisionClass(bucket: StrategyRelatedStock["decision_bucket"]): string {
  return `strategy-decision strategy-decision-${bucket}`;
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${(value * 100).toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}

function returnToneClass(value?: number | null): string {
  if (value === undefined || value === null || value === 0) {
    return "return-flat";
  }
  return value > 0 ? "return-up" : "return-down";
}
