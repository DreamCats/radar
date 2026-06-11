import { useState } from "react";
import { Activity, BarChart3, Database, Layers3, ListOrdered, MessageCircle, RadioTower, Search } from "lucide-react";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";

import { DashboardPage } from "./pages/DashboardPage";
import { IngestPage } from "./pages/IngestPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { OrganizePage } from "./pages/OrganizePage";
import { StrategyPage } from "./pages/StrategyPage";
import { WechatPage } from "./pages/WechatPage";

type TabKey = "dashboard" | "wechat" | "organize" | "leaderboard" | "strategy" | "ingest";

const NAV_ITEMS = [
  { key: "dashboard", label: "洞察", icon: Activity },
  { key: "wechat", label: "微信", icon: MessageCircle },
  { key: "organize", label: "整理", icon: Layers3 },
  { key: "leaderboard", label: "榜单", icon: ListOrdered },
  { key: "strategy", label: "策略", icon: Search },
  { key: "ingest", label: "作业", icon: Database },
] satisfies Array<{ key: TabKey; label: string; icon: typeof Activity }>;

export function App() {
  const [tab, setTab] = useState<TabKey>("dashboard");
  const shouldReduceMotion = useReducedMotion();

  return (
    <main className="app workspace-shell">
      <AmbientBackground shouldReduceMotion={shouldReduceMotion} />
      <aside className="sidebar">
        <div className="brand brand-block">
          <motion.span
            className="dot brand-dot"
            animate={shouldReduceMotion ? { opacity: 0.9 } : { opacity: [0.72, 1, 0.72], scale: [1, 1.16, 1] }}
            transition={shouldReduceMotion ? { duration: 0.12 } : { duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
          />
          <span>radar</span>
        </div>
        <LayoutGroup id="workspace-nav">
          <nav className="nav-group side-nav" aria-label="workspace sections">
          <div className="eyebrow">看板</div>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <motion.button
                className={tab === item.key ? "nav-item active" : "nav-item"}
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
                whileHover={shouldReduceMotion ? undefined : { x: 2 }}
                whileTap={shouldReduceMotion ? undefined : { scale: 0.985 }}
              >
                {tab === item.key && <motion.span className="nav-active-pill" layoutId="nav-active-pill" />}
                <span className="nav-item-content">
                  <Icon size={16} />
                  <span>{item.label}</span>
                </span>
              </motion.button>
            );
          })}
          </nav>
        </LayoutGroup>
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
        <div className="content">
          <div className="page-motion">
            {tab === "dashboard" && <DashboardPage />}
            {tab === "wechat" && <WechatPage />}
            {tab === "organize" && <OrganizePage />}
            {tab === "leaderboard" && <LeaderboardPage />}
            {tab === "strategy" && <StrategyPage />}
            {tab === "ingest" && <IngestPage />}
          </div>
        </div>
      </section>
    </main>
  );
}

function AmbientBackground({ shouldReduceMotion }: { shouldReduceMotion: boolean | null }) {
  const slowDrift = shouldReduceMotion
    ? { opacity: 0.24 }
    : { opacity: [0.18, 0.32, 0.22], x: ["-3%", "2%", "-1%"], y: ["0%", "4%", "-2%"] };
  const lowerDrift = shouldReduceMotion
    ? { opacity: 0.18 }
    : { opacity: [0.12, 0.24, 0.16], x: ["2%", "-2%", "3%"], y: ["2%", "-3%", "1%"] };

  return (
    <div className="ambient-background" aria-hidden="true">
      <div className="ambient-grid" />
      <motion.div
        className="ambient-sweep"
        animate={slowDrift}
        transition={shouldReduceMotion ? { duration: 0.12 } : { duration: 18, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="ambient-ribbon ambient-ribbon-primary"
        animate={slowDrift}
        transition={shouldReduceMotion ? { duration: 0.12 } : { duration: 14, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="ambient-ribbon ambient-ribbon-secondary"
        animate={lowerDrift}
        transition={shouldReduceMotion ? { duration: 0.12 } : { duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}
