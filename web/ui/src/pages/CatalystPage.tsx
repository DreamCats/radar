import { ListFilter, RefreshCw, Search, Settings2, Tags, X } from "lucide-react";
import { Fragment, useEffect, useMemo, useState, type CSSProperties } from "react";

import {
  fetchCatalystFeed,
  fetchCatalystTerms,
  resetCatalystTerms,
  saveCatalystTerms,
} from "../api/radarApi";
import { CatalystDetailDrawer, CatalystTermChip, highlightCatalystText } from "../components/CatalystEvidenceDrawer";
import { CatalystTermManager } from "../components/CatalystTermManager";
import { formatTime } from "../lib/datetime";
import { buildPresetRange, toLocalIso, type LocalRange, type RangePreset } from "../lib/timeRange";
import { useEscapeToClose } from "../lib/useEscapeToClose";
import { useSwipeToCloseSheet } from "../lib/useSwipeToCloseSheet";
import type {
  CatalystCategory,
  CatalystFeedItem,
  CatalystFeedPage,
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
    term_counts: {},
  },
};

const MOBILE_VISIBLE_CATEGORY_COUNT = 5;

export function CatalystPage() {
  const [library, setLibrary] = useState<CatalystTermLibrary | null>(null);
  const [page, setPage] = useState<CatalystFeedPage>(emptyPage);
  const [range, setRange] = useState<LocalRange>(() => buildPresetRange("yesterdayClose"));
  const [preset, setPreset] = useState<RangePreset>("yesterdayClose");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedTerm, setSelectedTerm] = useState<string | null>(null);
  const [keyword, setKeyword] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [managerOpen, setManagerOpen] = useState(false);
  const [mobileCategorySheetOpen, setMobileCategorySheetOpen] = useState(false);
  const [mobileTermSheetOpen, setMobileTermSheetOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedVersion, setFeedVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const selectedItem = useMemo(
    () => page.items.find((item) => item.key === selectedKey) ?? null,
    [page.items, selectedKey],
  );
  const activeCategory = useMemo(
    () => selectedCatalystCategory(library?.categories ?? [], selectedCategory),
    [library?.categories, selectedCategory],
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

  async function loadFeed(
    append: boolean,
    categoryId = selectedCategory,
    keywordValue = keyword,
    termValue: string | null = selectedTerm,
  ) {
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
        keyword: keywordValue.trim() || undefined,
        term_category_id: categoryId && termValue ? categoryId : undefined,
        term: termValue || undefined,
        dedupe: true,
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
      if (!append) {
        setFeedVersion((current) => current + 1);
        setSelectedKey(null);
      }
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
    setSelectedTerm(null);
    setMobileTermSheetOpen(false);
    setSelectedKey(null);
    void loadFeed(false, nextCategory, keyword, null);
  }

  function selectTerm(categoryId: string, term: string) {
    const nextTerm = selectedCategory === categoryId && selectedTerm === term ? null : term;
    setSelectedCategory(categoryId);
    setSelectedTerm(nextTerm);
    setSelectedKey(null);
    void loadFeed(false, categoryId, keyword, nextTerm);
  }

  function clearTerm(categoryId: string) {
    setSelectedCategory(categoryId);
    setSelectedTerm(null);
    setSelectedKey(null);
    void loadFeed(false, categoryId, keyword, null);
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
        <label className="field catalyst-keyword-field">
          <span>临时关键词</span>
          <input
            value={keyword}
            placeholder="AI液冷"
            onChange={(event) => {
              setKeyword(event.target.value);
              setSelectedTerm(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void loadFeed(false);
              }
            }}
          />
        </label>
        <div className="catalyst-action-row" role="group" aria-label="催化词操作">
          <button
            className="btn btn-sm catalyst-query-button"
            type="button"
            aria-label="查询催化词"
            title="查询"
            disabled={loading}
            onClick={() => void loadFeed(false)}
          >
            <Search size={14} />
            <span className="catalyst-button-label">查询</span>
          </button>
          <button
            className={loading ? "btn btn-sm catalyst-icon-button is-spinning" : "btn btn-sm catalyst-icon-button"}
            type="button"
            aria-label="刷新催化词"
            title="刷新"
            disabled={loading}
            onClick={() => void loadFeed(false)}
          >
            <RefreshCw size={14} />
          </button>
          <button
            className="btn btn-sm catalyst-library-button"
            type="button"
            aria-label="打开催化词词库"
            title="词库"
            onClick={() => setManagerOpen(true)}
          >
            <Settings2 size={14} />
            <span className="catalyst-button-label">词库</span>
          </button>
        </div>
      </div>

      {error && <p className="error-line">{error}</p>}

      <MobileCategoryStrip
        categories={library?.categories ?? []}
        counts={page.summary.category_counts}
        selectedCategory={selectedCategory}
        total={page.summary.available_total_items}
        onMore={() => {
          setMobileTermSheetOpen(false);
          setMobileCategorySheetOpen(true);
        }}
        onSelect={selectCategory}
      />
      <MobileTermTrigger
        category={activeCategory}
        count={page.summary.total_items}
        selectedTerm={selectedTerm}
        onOpen={() => {
          setMobileCategorySheetOpen(false);
          setMobileTermSheetOpen(true);
        }}
      />

      <div className="catalyst-workspace">
        <CategoryRail
          categories={library?.categories ?? []}
          counts={page.summary.category_counts}
          selectedCategory={selectedCategory}
          selectedTerm={selectedTerm}
          termCounts={page.summary.term_counts}
          total={page.summary.available_total_items}
          onSelect={selectCategory}
          onSelectTerm={selectTerm}
        />

        <section
          className={
            loading && page.items.length > 0
              ? "catalyst-feed-panel content-panel panel is-refreshing"
              : "catalyst-feed-panel content-panel panel"
          }
        >
          <header className="catalyst-feed-head">
            <div>
              <h2>催化词线索</h2>
              <span>
                {page.summary.total_items} 条线索 · {page.summary.total_messages} 条原文
                {page.summary.duplicate_messages > 0 ? ` · 合并 ${page.summary.duplicate_messages} 条` : ""}
              </span>
            </div>
            {loading && page.items.length > 0 && <span className="catalyst-refresh-state">更新中</span>}
          </header>
          <div className="catalyst-feed-list" aria-busy={loading} key={feedVersion}>
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

      {selectedItem && <CatalystDetailDrawer item={selectedItem} onClose={() => setSelectedKey(null)} />}

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

      {mobileTermSheetOpen && activeCategory && (
        <MobileTermSheet
          category={activeCategory}
          count={page.summary.total_items}
          selectedTerm={selectedTerm}
          termCounts={page.summary.term_counts}
          onClear={() => {
            clearTerm(activeCategory.id);
            setMobileTermSheetOpen(false);
          }}
          onClose={() => setMobileTermSheetOpen(false)}
          onSelectTerm={(categoryId, term) => {
            selectTerm(categoryId, term);
            setMobileTermSheetOpen(false);
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
  selectedTerm: string | null;
  termCounts: Record<string, Record<string, number>>;
  total: number;
  onSelect: (categoryId: string | null) => void;
  onSelectTerm: (categoryId: string, term: string) => void;
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
        <Fragment key={category.id}>
          <button
            className={props.selectedCategory === category.id ? "catalyst-category active" : "catalyst-category"}
            type="button"
            onClick={() => props.onSelect(category.id)}
          >
            <i style={{ backgroundColor: category.color }} />
            <span>{category.name}</span>
            <em>{props.counts[category.id] ?? 0}</em>
          </button>
          {props.selectedCategory === category.id && (
            <CategoryTermList
              category={category}
              selectedTerm={props.selectedTerm}
              termCounts={props.termCounts[category.id] ?? {}}
              onSelectTerm={props.onSelectTerm}
            />
          )}
        </Fragment>
      ))}
    </aside>
  );
}

function MobileTermTrigger(props: {
  category: CatalystCategory | null;
  count: number;
  selectedTerm: string | null;
  onOpen: () => void;
}) {
  const category = props.category;
  if (!category?.terms.length) {
    return null;
  }
  return (
    <button className="catalyst-mobile-term-trigger" type="button" onClick={props.onOpen}>
      <span>
        <ListFilter size={14} />
        {category.name}
      </span>
      <strong>{props.selectedTerm ?? "全部关键词"}</strong>
      <em>{props.count}</em>
    </button>
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
  const swipeClose = useSwipeToCloseSheet(props.onClose);
  useEscapeToClose(props.onClose);
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
        <header {...swipeClose}>
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

function MobileTermSheet(props: {
  category: CatalystCategory;
  count: number;
  selectedTerm: string | null;
  termCounts: Record<string, Record<string, number>>;
  onClear: () => void;
  onClose: () => void;
  onSelectTerm: (categoryId: string, term: string) => void;
}) {
  const swipeClose = useSwipeToCloseSheet(props.onClose);
  useEscapeToClose(props.onClose);
  return (
    <div
      className="catalyst-mobile-term-sheet-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          props.onClose();
        }
      }}
    >
      <aside className="catalyst-mobile-term-sheet panel" role="dialog" aria-modal="true" aria-label={`${props.category.name}关键词`}>
        <header {...swipeClose}>
          <div>
            <strong>{props.category.name}</strong>
            <span>{props.count} 条线索</span>
          </div>
          <button className="mini-button" type="button" title="关闭" onClick={props.onClose}>
            <X size={14} />
          </button>
        </header>
        <div className="catalyst-mobile-term-sheet-list">
          <button
            className={props.selectedTerm === null ? "catalyst-category active" : "catalyst-category"}
            type="button"
            onClick={props.onClear}
          >
            <i style={{ backgroundColor: props.category.color }} />
            <span>全部关键词</span>
            {props.selectedTerm === null && <em>{props.count}</em>}
          </button>
          <CategoryTermList
            category={props.category}
            selectedTerm={props.selectedTerm}
            termCounts={props.termCounts[props.category.id] ?? {}}
            onSelectTerm={props.onSelectTerm}
          />
        </div>
      </aside>
    </div>
  );
}

function CategoryTermList(props: {
  category: CatalystCategory;
  selectedTerm: string | null;
  termCounts: Record<string, number>;
  onSelectTerm: (categoryId: string, term: string) => void;
}) {
  if (!props.category.terms.length) {
    return null;
  }
  return (
    <div className="catalyst-category-terms" aria-label={`${props.category.name}关键词`}>
      {props.category.terms.map((term) => (
        <TermButton
          category={props.category}
          count={props.termCounts[term] ?? 0}
          key={term}
          selected={props.selectedTerm === term}
          term={term}
          onSelectTerm={props.onSelectTerm}
        />
      ))}
    </div>
  );
}

function TermButton(props: {
  category: CatalystCategory;
  count: number;
  selected: boolean;
  term: string;
  onSelectTerm: (categoryId: string, term: string) => void;
}) {
  return (
    <button
      className={props.selected ? "catalyst-category-term active" : "catalyst-category-term"}
      style={{ "--term-color": props.category.color } as CSSProperties}
      type="button"
      onClick={() => props.onSelectTerm(props.category.id, props.term)}
      title={props.term}
    >
      <i style={{ backgroundColor: props.category.color }} />
      <span>{props.term}</span>
      <em>{props.count}</em>
    </button>
  );
}

function selectedCatalystCategory(categories: CatalystCategory[], categoryId: string | null): CatalystCategory | null {
  if (!categoryId) {
    return null;
  }
  return categories.find((category) => category.id === categoryId) ?? null;
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
        {props.item.message_count > 1 && <b>连续 {props.item.message_count} 条</b>}
        {props.item.duplicate_count > 1 && <b>重复 {props.item.duplicate_count}</b>}
      </span>
      <span className="catalyst-chip-row">
        {props.item.matched_terms.slice(0, 6).map((hit) => (
          <CatalystTermChip hit={hit} key={`${hit.category_id}-${hit.term}`} />
        ))}
        {props.item.stock_mentions.map((stock) => (
          <span className="catalyst-stock-chip" key={`${stock.ts_code ?? ""}-${stock.stock_name}`}>
            {stock.stock_name}
          </span>
        ))}
      </span>
      <span className="catalyst-card-content">{highlightCatalystText(props.item.raw_content, props.item.matched_terms)}</span>
    </button>
  );
}
