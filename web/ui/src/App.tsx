import { useState } from "react";
import { Activity, BarChart3, Database, Inbox, RadioTower, RefreshCw, Search } from "lucide-react";

import { DashboardPage } from "./pages/DashboardPage";
import { IngestPage } from "./pages/IngestPage";
import { MessagesPage } from "./pages/MessagesPage";
import { RunsPage } from "./pages/RunsPage";

type TabKey = "dashboard" | "messages" | "runs" | "ingest";

const NAV_ITEMS = [
  { key: "dashboard", label: "总览", icon: Activity },
  { key: "messages", label: "消息", icon: Inbox },
  { key: "ingest", label: "拉取", icon: Database },
  { key: "runs", label: "运行", icon: RefreshCw },
] satisfies Array<{ key: TabKey; label: string; icon: typeof Activity }>;

export function App() {
  const [tab, setTab] = useState<TabKey>("dashboard");

  return (
    <main className="app workspace-shell">
      <aside className="sidebar">
        <div className="brand brand-block">
          <span className="dot brand-dot" />
          <span>radar</span>
        </div>
        <nav className="nav-group side-nav" aria-label="workspace sections">
          <div className="eyebrow">看板</div>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={tab === item.key ? "nav-item active" : "nav-item"}
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
              >
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className="nav-group module-stack">
          <div className="eyebrow">下一阶段</div>
          <button className="nav-item disabled" type="button" disabled>
            <RadioTower size={16} />
            信号雷达
            <span className="tag">阶段二</span>
          </button>
          <button className="nav-item disabled" type="button" disabled>
            <BarChart3 size={16} />
            行情
            <span className="tag">预留</span>
          </button>
          <button className="nav-item disabled" type="button" disabled>
            <Search size={16} />
            策略
            <span className="tag">预留</span>
          </button>
        </div>
      </aside>
      <section className="main workspace-main">
        <header className="topbar">
          <div className="topbar-title">
            <span className="title">{pageTitle(tab)}</span>
            <span className="caption">· local dashboard</span>
          </div>
          <div className="system-pill">
            <span className="pulse-dot" />
            本地数据核
          </div>
          <button className="btn btn-primary btn-sm" type="button" onClick={() => setTab("ingest")}>
            <RefreshCw size={14} />
            拉取
          </button>
        </header>
        <div className="content">
          {tab === "dashboard" && <DashboardPage onOpenMessages={() => setTab("messages")} />}
          {tab === "messages" && <MessagesPage />}
          {tab === "runs" && <RunsPage />}
          {tab === "ingest" && <IngestPage />}
        </div>
      </section>
    </main>
  );
}

function pageTitle(tab: TabKey): string {
  const titles: Record<TabKey, string> = {
    dashboard: "原数据总览",
    messages: "消息查询",
    runs: "运行记录",
    ingest: "手动拉取",
  };
  return titles[tab];
}
