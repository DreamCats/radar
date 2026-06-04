import { useEffect, useState } from "react";
import { Search } from "lucide-react";

import { fetchMessages } from "../api/radarApi";
import { DateField, SelectField, TextField } from "../components/FormFields";
import { MessageRow } from "../components/MessageRow";
import { PanelTitle } from "../components/PanelTitle";
import { toIso } from "../lib/datetime";
import type { MessagePage, MessageQuery } from "../types";

const defaultQuery: MessageQuery = {
  source: "group_message",
  limit: 50,
};

export function MessagesPage() {
  const [query, setQuery] = useState<MessageQuery>(defaultQuery);
  const [page, setPage] = useState<MessagePage>({ items: [] });
  const [history, setHistory] = useState<MessageQuery[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(nextQuery: MessageQuery, pushHistory = false) {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMessages(nextQuery);
      setPage(data);
      setQuery(nextQuery);
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

  return (
    <section className="layout-grid">
      <MessageFilters
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
  loading: boolean;
  query: MessageQuery;
  onChange: (query: MessageQuery) => void;
  onSubmit: () => void;
}) {
  return (
    <form
      className="filter-panel"
      onSubmit={(event) => {
        event.preventDefault();
        props.onSubmit();
      }}
    >
      <SelectField
        label="来源"
        value={props.query.source ?? ""}
        onChange={(value) => props.onChange({ ...props.query, source: value })}
        options={[
          ["", "全部"],
          ["personal_message", "个人消息"],
          ["group_message", "个人群"],
        ]}
      />
      <TextField
        label="群名"
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
      <button className="primary-button" type="submit" disabled={props.loading}>
        <Search size={16} />
        查询
      </button>
    </form>
  );
}

function MessageResults(props: {
  canPrev: boolean;
  error: string | null;
  loading: boolean;
  page: MessagePage;
  onNext: () => void;
  onPrev: () => void;
}) {
  const canNext = Boolean(props.page.next_cursor_time && props.page.next_cursor_id);
  return (
    <div className="content-panel">
      <PanelTitle title="消息流" meta={`${props.page.items.length} 条`} />
      {props.error && <p className="error-line">{props.error}</p>}
      <div className="message-list">
        {props.page.items.map((item) => (
          <MessageRow key={item.message_id} item={item} />
        ))}
        {!props.loading && props.page.items.length === 0 && <p className="empty-line">暂无数据</p>}
      </div>
      <div className="pager">
        <button
          className="icon-button"
          type="button"
          disabled={!props.canPrev || props.loading}
          onClick={props.onPrev}
          title="上一页"
        >
          上一页
        </button>
        <button
          className="icon-button"
          type="button"
          disabled={!canNext || props.loading}
          onClick={props.onNext}
          title="下一页"
        >
          下一页
        </button>
      </div>
    </div>
  );
}
