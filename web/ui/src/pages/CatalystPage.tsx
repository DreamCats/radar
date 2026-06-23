import { Copy, ListFilter, RefreshCw, Search, Settings2, Tags, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

import {
  fetchCatalystFeed,
  fetchCatalystTerms,
  resetCatalystTerms,
  saveCatalystTerms,
} from "../api/radarApi";
import { CatalystTermManager } from "../components/CatalystTermManager";
import { copyText } from "../lib/clipboard";
import { formatTime } from "../lib/datetime";
import { buildPresetRange, toLocalIso, type LocalRange, type RangePreset } from "../lib/timeRange";
import type {
  CatalystCategory,
  CatalystFeedItem,
  CatalystFeedPage,
  CatalystTermHit,
  CatalystTermLibrary,
} from "../types";

const CATALYST_RANGE_PRESETS: Array<[RangePreset, string]> = [
  ["yesterdayClose", "昨日 15:00"],
  ["twoDaysClose", "前天 15:00"],
  ["last7d", "近 7 日"],
  ["custom", "自定义"],
];

const emptyPage: CatalystFeedPage = {
  items: [],
  summary: {
    total_items: 0,
    total_messages: 0,
    duplicate_messages: 0,
    available_total_items: 0,
    category_counts: {},
  },
};

const MOBILE_VISIBLE_CATEGORY_COUNT = 5;

export function CatalystPage() {
  const [library, setLibrary] = useState<CatalystTermLibrary | null>(null);
  const [page, setPage] = useState<CatalystFeedPage>(emptyPage);
  const [range, setRange] = useState<LocalRange>(() => buildPresetRange("yesterdayClose"));
  const [preset, setPreset] = useState<RangePreset>("yesterdayClose");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [keyword, setKeyword] = useState("");
  const [dedupe, setDedupe] = useState(true);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [managerOpen, setManagerOpen] = useState(false);
  const [mobileCategorySheetOpen, setMobileCategorySheetOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedItem = useMemo(
    () => page.items.find((item) => item.key === selectedKey) ?? null,
    [page.items, selectedKey],
  );

  useEffect(() => {
    void loadTerms();
    void loadFeed(false);
  }, []);

  async function loadTerms() {
    try {
      const data = await fetchCatalystTerms();
      setLibrary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取词库失败");
    }
  }

  async function loadFeed(append: boolean, categoryId = selectedCategory) {
    const start = toLocalIso(range.startDate, range.startTime);
    const end = toLocalIso(range.endDate, range.endTime);
    if (!start || !end) {
      setError("请填写完整时间范围");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCatalystFeed({
        start_time: start,
        end_time: end,
        category_ids: categoryId ? [categoryId] : undefined,
        keyword: keyword.trim() || undefined,
        dedupe,
        cursor_time: append ? page.next_cursor_time : undefined,
        cursor_key: append ? page.next_cursor_key : undefined,
        limit: 60,
      });
      setPage((current) =>
        append
          ? {
              ...data,
              items: [...current.items, ...data.items],
            }
          : data,
      );
      setSelectedKey((current) => (append ? current : null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "查询失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveTerms(next: CatalystTermLibrary) {
    setSaving(true);
    try {
      const saved = await saveCatalystTerms(next);
      setLibrary(saved);
      setManagerOpen(false);
      await loadFeed(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存词库失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleResetTerms() {
    setSaving(true);
    try {
      const reset = await resetCatalystTerms();
      setLibrary(reset);
      setManagerOpen(false);
      await loadFeed(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "恢复默认失败");
    } finally {
      setSaving(false);
    }
  }

  function selectPreset(next: RangePreset) {
    setPreset(next);
    if (next !== "custom") {
      setRange(buildPresetRange(next));
    }
  }

  function selectCategory(categoryId: string | null) {
    const nextCategory = selectedCategory === categoryId ? null : categoryId;
    setSelectedCategory(nextCategory);
    setSelectedKey(null);
    void loadFeed(false, nextCategory);
  }

  return (
    <section className="catalyst-page" data-range-preset={preset}>
      <div className="catalyst-control-bar filter-panel">
        <div className="catalyst-window-tabs" role="tablist" aria-label="催化词时间窗口">
          {CATALYST_RANGE_PRESETS.map(([key, label]) => (
            <button
              className={preset === key ? "active" : ""}
              key={key}
              type="button"
              role="tab"
              aria-selected={preset === key}
              onClick={() => selectPreset(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="field catalyst-datetime-field">
          <span>起点</span>
          <input
            type="datetime-local"
            value={`${range.startDate}T${range.startTime}`}
            onChange={(event) => {
              const [date, time = "00:00"] = event.target.value.split("T");
              setPreset("custom");
              setRange((current) => ({ ...current, startDate: date, startTime: time.slice(0, 5) }));
            }}
          />
        </label>
        <label className="field catalyst-datetime-field">
          <span>终点</span>
          <input
            type="datetime-local"
            value={`${range.endDate}T${range.endTime}`}
            onChange={(event) => {
              const [date, time = "00:00"] = event.target.value.split("T");
              setPreset("custom");
              setRange((current) => ({ ...current, endDate: date, endTime: time.slice(0, 5) }));
            }}
          />
        </label>
        <label className="field">
          <span>临时关键词</span>
          <input value={keyword} placeholder="AI液冷" onChange={(event) => setKeyword(event.target.value)} />
        </label>
        <label className="catalyst-dedupe-toggle">
          <input type="checkbox" checked={dedupe} onChange={(event) => setDedupe(event.target.checked)} />
          <span>去重</span>
        </label>
        <button
          className="btn btn-sm catalyst-query-button"
          type="button"
          disabled={loading}
          onClick={() => void loadFeed(false)}
        >
          <Search size={14} />
          查询
        </button>
        <button
          className="btn btn-sm catalyst-icon-button"
          type="button"
          title="刷新"
          disabled={loading}
          onClick={() => void loadFeed(false)}
        >
          <RefreshCw size={14} />
        </button>
        <button className="btn btn-sm" type="button" onClick={() => setManagerOpen(true)}>
          <Settings2 size={14} />
          词库
        </button>
      </div>

      {error && <p className="error-line">{error}</p>}

      <MobileCategoryStrip
        categories={library?.categories ?? []}
        counts={page.summary.category_counts}
        selectedCategory={selectedCategory}
        total={page.summary.available_total_items}
        onMore={() => setMobileCategorySheetOpen(true)}
        onSelect={selectCategory}
      />

      <div className="catalyst-workspace">
        <CategoryRail
          categories={library?.categories ?? []}
          counts={page.summary.category_counts}
          selectedCategory={selectedCategory}
          total={page.summary.available_total_items}
          onSelect={selectCategory}
        />

        <section className="catalyst-feed-panel content-panel panel">
          <header className="catalyst-feed-head">
            <div>
              <h2>催化词线索</h2>
              <span>
                {page.summary.total_items} 条线索 · {page.summary.total_messages} 条原文
                {page.summary.duplicate_messages > 0 ? ` · 去重 ${page.summary.duplicate_messages} 条` : ""}
              </span>
            </div>
          </header>
          <div className="catalyst-feed-list" aria-busy={loading}>
            {loading && page.items.length === 0 && <p className="empty-line">正在扫描消息。</p>}
            {page.items.map((item) => (
              <CatalystCard
                active={item.key === selectedKey}
                item={item}
                key={item.key}
                onSelect={() => setSelectedKey(item.key)}
              />
            ))}
            {!loading && page.items.length === 0 && <p className="empty-line">当前窗口没有命中催化词</p>}
            {page.next_cursor_key && (
              <button className="wechat-thread-older" type="button" disabled={loading} onClick={() => void loadFeed(true)}>
                {loading ? "加载中" : "加载更多"}
              </button>
            )}
          </div>
        </section>
      </div>

      {selectedItem && <CatalystDetail item={selectedItem} onClose={() => setSelectedKey(null)} />}

      {mobileCategorySheetOpen && (
        <MobileCategorySheet
          categories={library?.categories ?? []}
          counts={page.summary.category_counts}
          selectedCategory={selectedCategory}
          total={page.summary.available_total_items}
          onClose={() => setMobileCategorySheetOpen(false)}
          onSelect={(categoryId) => {
            selectCategory(categoryId);
            setMobileCategorySheetOpen(false);
          }}
        />
      )}

      {managerOpen && library && (
        <CatalystTermManager
          library={library}
          saving={saving}
          onClose={() => setManagerOpen(false)}
          onReset={handleResetTerms}
          onSave={handleSaveTerms}
        />
      )}
    </section>
  );
}

function MobileCategoryStrip(props: {
  categories: CatalystCategory[];
  counts: Record<string, number>;
  selectedCategory: string | null;
  total: number;
  onMore: () => void;
  onSelect: (categoryId: string | null) => void;
}) {
  const visibleCategories = mobileVisibleCategories(props.categories, props.counts, props.selectedCategory);
  return (
    <div className="catalyst-mobile-category-strip" aria-label="催化词移动端标签">
      <button
        className={props.selectedCategory === null ? "catalyst-mobile-category-chip active" : "catalyst-mobile-category-chip"}
        type="button"
        onClick={() => props.onSelect(null)}
      >
        <span>全部</span>
        <em>{props.total}</em>
      </button>
      {visibleCategories.map((category) => (
        <button
          className={
            props.selectedCategory === category.id ? "catalyst-mobile-category-chip active" : "catalyst-mobile-category-chip"
          }
          key={category.id}
          type="button"
          onClick={() => props.onSelect(category.id)}
        >
          <i style={{ backgroundColor: category.color }} />
          <span>{category.name}</span>
          <em>{props.counts[category.id] ?? 0}</em>
        </button>
      ))}
      {props.categories.length > visibleCategories.length && (
        <button className="catalyst-mobile-category-chip more" type="button" onClick={props.onMore}>
          <ListFilter size={14} />
          <span>更多</span>
        </button>
      )}
    </div>
  );
}

function CategoryRail(props: {
  categories: CatalystCategory[];
  counts: Record<string, number>;
  selectedCategory: string | null;
  total: number;
  onSelect: (categoryId: string | null) => void;
}) {
  return (
    <aside className="catalyst-category-panel content-panel panel">
      <div className="catalyst-category-head">
        <Tags size={15} />
        <strong>标签</strong>
      </div>
      <button
        className={props.selectedCategory === null ? "catalyst-category active" : "catalyst-category"}
        type="button"
        onClick={() => props.onSelect(null)}
      >
        <span>全部</span>
        <em>{props.total}</em>
      </button>
      {props.categories.map((category) => (
        <button
          className={props.selectedCategory === category.id ? "catalyst-category active" : "catalyst-category"}
          key={category.id}
          type="button"
          onClick={() => props.onSelect(category.id)}
        >
          <i style={{ backgroundColor: category.color }} />
          <span>{category.name}</span>
          <em>{props.counts[category.id] ?? 0}</em>
        </button>
      ))}
    </aside>
  );
}

function MobileCategorySheet(props: {
  categories: CatalystCategory[];
  counts: Record<string, number>;
  selectedCategory: string | null;
  total: number;
  onClose: () => void;
  onSelect: (categoryId: string | null) => void;
}) {
  return (
    <div
      className="catalyst-mobile-category-sheet-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          props.onClose();
        }
      }}
    >
      <aside className="catalyst-mobile-category-sheet panel" role="dialog" aria-modal="true" aria-label="选择催化词标签">
        <header>
          <div>
            <strong>标签</strong>
            <span>选择一个维度筛选 feed</span>
          </div>
          <button className="mini-button" type="button" title="关闭" onClick={props.onClose}>
            <X size={14} />
          </button>
        </header>
        <div className="catalyst-mobile-category-sheet-list">
          <button
            className={props.selectedCategory === null ? "catalyst-category active" : "catalyst-category"}
            type="button"
            onClick={() => props.onSelect(null)}
          >
            <span>全部</span>
            <em>{props.total}</em>
          </button>
          {props.categories.map((category) => (
            <button
              className={props.selectedCategory === category.id ? "catalyst-category active" : "catalyst-category"}
              key={category.id}
              type="button"
              onClick={() => props.onSelect(category.id)}
            >
              <i style={{ backgroundColor: category.color }} />
              <span>{category.name}</span>
              <em>{props.counts[category.id] ?? 0}</em>
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}

function mobileVisibleCategories(
  categories: CatalystCategory[],
  counts: Record<string, number>,
  selectedCategory: string | null,
) {
  const sorted = [...categories].sort((left, right) => (counts[right.id] ?? 0) - (counts[left.id] ?? 0));
  const visible = sorted.slice(0, MOBILE_VISIBLE_CATEGORY_COUNT);
  const selected = selectedCategory ? categories.find((category) => category.id === selectedCategory) : undefined;
  if (selected && !visible.some((category) => category.id === selected.id)) {
    return [selected, ...visible.slice(0, MOBILE_VISIBLE_CATEGORY_COUNT - 1)];
  }
  return visible;
}

function CatalystCard(props: { item: CatalystFeedItem; active: boolean; onSelect: () => void }) {
  const conversation = props.item.source === "个人群" ? props.item.group_name : props.item.sender;
  return (
    <button
      className={props.active ? "catalyst-card active" : "catalyst-card"}
      type="button"
      onClick={props.onSelect}
    >
      <span className="catalyst-card-meta">
        <strong>{formatTime(props.item.first_message_time)}</strong>
        <em>{conversation || props.item.sender}</em>
        {props.item.duplicate_count > 1 && <b>重复 {props.item.duplicate_count}</b>}
      </span>
      <span className="catalyst-chip-row">
        {props.item.matched_terms.slice(0, 6).map((hit) => (
          <Chip hit={hit} key={`${hit.category_id}-${hit.term}`} />
        ))}
        {props.item.stock_mentions.map((stock) => (
          <span className="catalyst-stock-chip" key={`${stock.ts_code ?? ""}-${stock.stock_name}`}>
            {stock.stock_name}
          </span>
        ))}
      </span>
      <span className="catalyst-card-content">{highlightText(props.item.raw_content, props.item.matched_terms)}</span>
    </button>
  );
}

function CatalystDetail({ item, onClose }: { item: CatalystFeedItem; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.isComposing) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="catalyst-detail-drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <aside className="catalyst-detail-panel catalyst-detail-drawer content-panel panel" role="dialog" aria-modal="true">
        <header className="catalyst-detail-head">
          <div>
            <h2>原文证据</h2>
            <span>最早 {formatTime(item.first_message_time)} · 最新 {formatTime(item.latest_message_time)}</span>
          </div>
          <div className="catalyst-detail-actions">
            <button
              className="mini-button"
              type="button"
              title="复制原文"
              onClick={() => {
                void copyText(item.raw_content).then(() => {
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 1200);
                });
              }}
            >
              <Copy size={14} />
            </button>
            <button className="mini-button" type="button" title="关闭详情" onClick={onClose}>
              <X size={14} />
            </button>
          </div>
        </header>
        {copied && <p className="catalyst-copy-state">已复制</p>}
        <div className="catalyst-chip-row detail">
          {item.matched_terms.map((hit) => (
            <Chip hit={hit} key={`${hit.category_id}-${hit.term}`} />
          ))}
          {item.stock_mentions.map((stock) => (
            <span className="catalyst-stock-chip" key={`${stock.ts_code ?? ""}-${stock.stock_name}`}>
              {stock.stock_name}
            </span>
          ))}
        </div>
        <p className="catalyst-full-content">{highlightText(item.raw_content, item.matched_terms)}</p>
        <div className="catalyst-duplicates">
          <strong>重复来源</strong>
          {item.duplicate_sources.map((source) => (
            <span key={source.message_id}>
              <em>{formatTime(source.message_time)}</em>
              {source.source === "个人群" ? source.group_name : source.sender}
              <small>{source.sender}</small>
            </span>
          ))}
        </div>
      </aside>
    </div>
  );
}

function Chip({ hit }: { hit: CatalystTermHit }) {
  return (
    <span className="catalyst-term-chip" style={{ "--chip-color": hit.color } as CSSProperties}>
      {hit.category_name} · {hit.term}
    </span>
  );
}

function highlightText(text: string, hits: CatalystTermHit[]) {
  const terms = Array.from(new Set(hits.map((hit) => hit.term).filter(Boolean))).sort((a, b) => b.length - a.length);
  if (terms.length === 0) {
    return text;
  }
  const pattern = new RegExp(`(${terms.map(escapeRegex).join("|")})`, "gi");
  return text.split(pattern).map((part, index) => {
    const matched = terms.some((term) => term.toLowerCase() === part.toLowerCase());
    return matched ? <mark key={`${part}-${index}`}>{part}</mark> : <span key={`${part}-${index}`}>{part}</span>;
  });
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
