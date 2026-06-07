import { useState } from "react";
import { Activity, BarChart3, Database, Layers3, ListOrdered, MessageCircle, RadioTower, RefreshCw, Search } from "lucide-react";

import { DashboardPage } from "./pages/DashboardPage";
import { IngestPage } from "./pages/IngestPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { MessagesPage } from "./pages/MessagesPage";
import { OrganizePage } from "./pages/OrganizePage";
import { StrategyPage } from "./pages/StrategyPage";
import { WechatPage } from "./pages/WechatPage";

type TabKey = "dashboard" | "wechat" | "messages" | "organize" | "leaderboard" | "strategy" | "ingest";

const NAV_ITEMS = [
  { key: "dashboard", label: "总览", icon: Activity },
  { key: "wechat", label: "微信", icon: MessageCircle },
  { key: "organize", label: "整理", icon: Layers3 },
  { key: "leaderboard", label: "榜单", icon: ListOrdered },
  { key: "strategy", label: "策略", icon: Search },
  { key: "ingest", label: "作业", icon: Database },
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
            作业
          </button>
        </header>
        <div className="content">
          {tab === "dashboard" && <DashboardPage onOpenStrategy={() => setTab("strategy")} />}
          {tab === "wechat" && <WechatPage />}
          {tab === "messages" && <MessagesPage />}
          {tab === "organize" && <OrganizePage />}
          {tab === "leaderboard" && <LeaderboardPage />}
          {tab === "strategy" && <StrategyPage />}
          {tab === "ingest" && <IngestPage />}
        </div>
      </section>
    </main>
  );
}

function pageTitle(tab: TabKey): string {
  const titles: Record<TabKey, string> = {
    dashboard: "数据概览",
    wechat: "微信消息",
    messages: "消息查询",
    organize: "消息整理",
    leaderboard: "推荐胜率榜",
    strategy: "发酵确认策略",
    ingest: "作业中心",
  };
  return titles[tab];
}
