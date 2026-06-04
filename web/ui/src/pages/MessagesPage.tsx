import { useEffect, useId, useMemo, useState } from "react";
import { Search } from "lucide-react";

import { fetchMessageGroups, fetchMessages } from "../api/radarApi";
import { DateField, SelectField, TextField } from "../components/FormFields";
import { PanelTitle } from "../components/PanelTitle";
import { formatTime, toIso } from "../lib/datetime";
import type { MessageItem, MessagePage, MessageQuery } from "../types";

const defaultQuery: MessageQuery = {
  source: "group_message",
  limit: 50,
};

export function MessagesPage() {
  const [query, setQuery] = useState<MessageQuery>(defaultQuery);
  const [page, setPage] = useState<MessagePage>({ items: [] });
  const [history, setHistory] = useState<MessageQuery[]>([]);
  const [groupNames, setGroupNames] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(nextQuery: MessageQuery, pushHistory = false) {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMessages(nextQuery);
      setPage(data);
      setQuery(nextQuery);
      setSelectedId(data.items[0]?.message_id ?? null);
      if (pushHistory) {
        setHistory((items) => [...items, query]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "查询失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(defaultQuery);
  }, []);

  useEffect(() => {
    const source = query.source;
    if (source === "personal_message") {
      setGroupNames([]);
      return;
    }
    void fetchMessageGroups({ source: source || "group_message", limit: 200 })
      .then((groups) => setGroupNames(groups.map((item) => item.group_name)))
      .catch(() => setGroupNames([]));
  }, [query.source]);

  return (
    <section className="message-query-page">
      <MessageFilters
        groupNames={groupNames}
        loading={loading}
        query={query}
        onChange={setQuery}
        onSubmit={() => {
          setHistory([]);
          void load({ ...query, cursor_time: undefined, cursor_id: undefined });
        }}
      />
      <MessageResults
        canPrev={history.length > 0}
        error={error}
        loading={loading}
        page={page}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onNext={() =>
          void load(
            {
              ...query,
              cursor_time: page.next_cursor_time ?? undefined,
              cursor_id: page.next_cursor_id ?? undefined,
            },
            true,
          )
        }
        onPrev={() => {
          const previous = history[history.length - 1];
          if (previous) {
            setHistory((items) => items.slice(0, -1));
            void load(previous);
          }
        }}
      />
    </section>
  );
}

function MessageFilters(props: {
  groupNames: string[];
  loading: boolean;
  query: MessageQuery;
  onChange: (query: MessageQuery) => void;
  onSubmit: () => void;
}) {
  return (
    <form
      className="filter-panel message-filter-bar"
      onSubmit={(event) => {
        event.preventDefault();
        props.onSubmit();
      }}
    >
      <SelectField
        label="来源"
        value={props.query.source ?? ""}
        onChange={(value) =>
          props.onChange({
            ...props.query,
            source: value,
            group_name: value === "personal_message" ? "" : props.query.group_name,
          })
        }
        options={[
          ["", "全部"],
          ["personal_message", "个人消息"],
          ["group_message", "个人群"],
        ]}
      />
      <GroupNameField
        groups={props.groupNames}
        value={props.query.group_name ?? ""}
        onChange={(value) => props.onChange({ ...props.query, group_name: value })}
      />
      <TextField
        label="关键词"
        value={props.query.keyword ?? ""}
        onChange={(value) => props.onChange({ ...props.query, keyword: value })}
      />
      <DateField
        label="开始"
        value={props.query.start_time ?? ""}
        onChange={(value) => props.onChange({ ...props.query, start_time: toIso(value) })}
      />
      <DateField
        label="结束"
        value={props.query.end_time ?? ""}
        onChange={(value) => props.onChange({ ...props.query, end_time: toIso(value) })}
      />
      <button className="btn btn-primary" type="submit" disabled={props.loading}>
        <Search size={16} />
        查询
      </button>
    </form>
  );
}

function GroupNameField(props: {
  groups: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  const inputId = useId();
  const [open, setOpen] = useState(false);
  const options = useMemo(() => {
    const keyword = props.value.trim().toLocaleLowerCase();
    const matched = keyword
      ? props.groups.filter((name) => name.toLocaleLowerCase().includes(keyword))
      : props.groups;
    return matched.slice(0, 40);
  }, [props.groups, props.value]);
  const shouldShow = open && props.groups.length > 0;

  return (
    <div className="field message-group-field">
      <label htmlFor={inputId}>群名</label>
      <div className="message-group-control">
        <input
          id={inputId}
          value={props.value}
          autoComplete="off"
          onBlur={() => setOpen(false)}
          onChange={(event) => {
            props.onChange(event.target.value);
            setOpen(true);
          }}
          onClick={() => setOpen(true)}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
            }
          }}
        />
        <span className="message-group-caret" aria-hidden="true" />
        {shouldShow && (
          <div className="message-group-menu" onMouseDown={(event) => event.preventDefault()}>
            {options.length > 0 ? (
              options.map((name) => (
                <button
                  className="message-group-option"
                  key={name}
                  type="button"
                  onMouseDown={() => {
                    props.onChange(name);
                    setOpen(false);
                  }}
                >
                  {name}
                </button>
              ))
            ) : (
              <span className="message-group-empty">没有匹配的群名</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MessageResults(props: {
  canPrev: boolean;
  error: string | null;
  loading: boolean;
  page: MessagePage;
  selectedId: string | null;
  onSelect: (messageId: string) => void;
  onNext: () => void;
  onPrev: () => void;
}) {
  const canNext = Boolean(props.page.next_cursor_time && props.page.next_cursor_id);
  const selected = props.page.items.find((item) => item.message_id === props.selectedId) ?? props.page.items[0] ?? null;
  return (
    <div className="message-workspace">
      <div className="content-panel panel message-results-panel">
        <PanelTitle title="消息流" meta={`${props.page.items.length} 条`} />
        {props.error && <p className="error-line">{props.error}</p>}
        <div className="message-table-head">
          <span>时间</span>
          <span>来源</span>
          <span>群 / 发送人</span>
          <span>内容</span>
        </div>
        <div className="message-list message-table-body">
          {props.page.items.map((item) => (
            <MessageListRow
              active={item.message_id === selected?.message_id}
              item={item}
              key={item.message_id}
              onSelect={() => props.onSelect(item.message_id)}
            />
          ))}
          {!props.loading && props.page.items.length === 0 && <p className="empty-line">暂无数据</p>}
        </div>
        <div className="pager">
          <button
            className="btn"
            type="button"
            disabled={!props.canPrev || props.loading}
            onClick={props.onPrev}
            title="上一页"
          >
            上一页
          </button>
          <button
            className="btn"
            type="button"
            disabled={!canNext || props.loading}
            onClick={props.onNext}
            title="下一页"
          >
            下一页
          </button>
        </div>
      </div>
      <MessageDetailPanel item={selected} />
    </div>
  );
}

function MessageListRow(props: {
  active: boolean;
  item: MessageItem;
  onSelect: () => void;
}) {
  return (
    <button className={props.active ? "message-list-row active" : "message-list-row"} type="button" onClick={props.onSelect}>
      <span className="message-time">{formatTime(props.item.message_time)}</span>
      <span className="message-source">{props.item.source}</span>
      <span className="message-identity">
        <strong>{props.item.group_name || "-"}</strong>
        <em>{props.item.sender}</em>
      </span>
      <span className="message-summary">{props.item.raw_content}</span>
    </button>
  );
}

function MessageDetailPanel({ item }: { item: MessageItem | null }) {
  return (
    <aside className="content-panel panel message-detail-panel">
      <PanelTitle title="详情" meta={item ? formatTime(item.message_time) : "未选择"} />
      {item ? (
        <div className="message-detail-body">
          <div className="detail-meta-grid">
            <span>来源</span>
            <strong>{item.source}</strong>
            <span>群</span>
            <strong>{item.group_name || "-"}</strong>
            <span>发送人</span>
            <strong>{item.sender}</strong>
            <span>ID</span>
            <strong>{item.message_id}</strong>
          </div>
          <p>{item.raw_content}</p>
        </div>
      ) : (
        <p className="empty-line">选择一条消息查看详情</p>
      )}
    </aside>
  );
}
