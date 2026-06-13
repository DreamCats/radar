import { useId, useMemo, useState } from "react";
import { Search } from "lucide-react";

import { SelectField, TextField } from "./FormFields";
import { avatarText } from "../lib/wechat";
import type { MessageConversationQuery } from "../types";

export function WechatFilters(props: {
  groupNames: string[];
  groupNamesLoading: boolean;
  loading: boolean;
  query: MessageConversationQuery;
  onChange: (query: MessageConversationQuery) => void;
  onSubmit: () => void;
}) {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const nameLabel =
    props.query.source === "personal_message" ? "人名" : props.query.source === "group_message" ? "群名" : "群名/人名";

  return (
    <form
      className={filtersOpen ? "filter-panel wechat-filter-bar mobile-open" : "filter-panel wechat-filter-bar"}
      onSubmit={(event) => {
        event.preventDefault();
        setFiltersOpen(false);
        props.onSubmit();
      }}
    >
      <button
        className="mobile-filter-toggle"
        type="button"
        aria-expanded={filtersOpen}
        onClick={() => setFiltersOpen((value) => !value)}
      >
        微信筛选
        <span>{wechatFilterSummary(props.query)}</span>
      </button>
      <div className="mobile-filter-fields">
        <SelectField
          label="来源"
          value={props.query.source ?? ""}
          onChange={(value) =>
            props.onChange({
              ...props.query,
              source: value,
              group_name: "",
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
          label={nameLabel}
          loading={props.groupNamesLoading}
          value={props.query.group_name ?? ""}
          onChange={(value) => props.onChange({ ...props.query, group_name: value })}
        />
        <TextField
          label="关键词"
          value={props.query.keyword ?? ""}
          onChange={(value) => props.onChange({ ...props.query, keyword: value })}
        />
        <button className="btn btn-primary" type="submit" disabled={props.loading}>
          <Search size={16} />
          查询
        </button>
      </div>
    </form>
  );
}

function wechatFilterSummary(query: MessageConversationQuery): string {
  const source = query.source === "personal_message" ? "个人消息" : query.source === "group_message" ? "个人群" : "全部来源";
  return [source, query.group_name || "", query.keyword || ""].filter(Boolean).join(" · ");
}

export function Avatar({ name, small = false }: { name: string; small?: boolean }) {
  return <span className={small ? "wechat-avatar small" : "wechat-avatar"}>{avatarText(name)}</span>;
}

function GroupNameField(props: {
  groups: string[];
  label: string;
  loading: boolean;
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
  const shouldShow = open && (props.loading || props.groups.length > 0);

  return (
    <div className="field message-group-field">
      <label htmlFor={inputId}>{props.label}</label>
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
            {props.loading ? (
              <span className="message-group-empty">正在加载{props.label}</span>
            ) : options.length > 0 ? (
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
              <span className="message-group-empty">没有匹配的{props.label}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
