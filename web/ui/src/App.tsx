import { useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  Database,
  Layers3,
  ListOrdered,
  LogOut,
  MessageCircle,
  Network,
  RadioTower,
  Search,
} from "lucide-react";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";

import { fetchAuthStatus, login, logout } from "./api/radarApi";
import { DashboardPage } from "./pages/DashboardPage";
import { IngestPage } from "./pages/IngestPage";
import { IndustryChainPage } from "./pages/IndustryChainPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { LoginPage } from "./pages/LoginPage";
import { OrganizePage } from "./pages/OrganizePage";
import { StrategyPage } from "./pages/StrategyPage";
import { WechatPage } from "./pages/WechatPage";
import type { AuthStatus } from "./types";

type TabKey = "dashboard" | "wechat" | "organize" | "industry-chain" | "leaderboard" | "strategy" | "ingest";

const NAV_ITEMS = [
  { key: "dashboard", label: "洞察", icon: Activity },
  { key: "wechat", label: "微信", icon: MessageCircle },
  { key: "organize", label: "整理", icon: Layers3 },
  { key: "industry-chain", label: "产业链", icon: Network },
  { key: "leaderboard", label: "榜单", icon: ListOrdered },
  { key: "strategy", label: "策略", icon: Search },
  { key: "ingest", label: "作业", icon: Database },
] satisfies Array<{ key: TabKey; label: string; icon: typeof Activity }>;

const TAB_STORAGE_KEY = "radar.activeTab";
const TAB_KEYS = new Set<TabKey>(NAV_ITEMS.map((item) => item.key));

export function App() {
  const [tab, setTab] = useState<TabKey>(() => readInitialTab());
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const shouldReduceMotion = useReducedMotion();

  useEffect(() => {
    fetchAuthStatus()
      .then((next) => {
        setAuth(next);
        setAuthError(null);
      })
      .catch((err) => {
        setAuthError(err instanceof Error ? err.message : "无法读取登录状态");
        setAuth({ auth_required: true, authenticated: false });
      });
  }, []);

  useEffect(() => {
    persistActiveTab(tab);
  }, [tab]);

  useEffect(() => {
    const onPopState = () => {
      const nextTab = readInitialTab();
      setTab((current) => (current === nextTab ? current : nextTab));
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  async function handleLogin(username: string, password: string) {
    const next = await login(username, password);
    setAuth(next);
    setAuthError(null);
  }

  async function handleLogout() {
    const next = await logout();
    setAuth(next);
    setTab("dashboard");
  }

  if (auth === null) {
    return (
      <main className="app workspace-shell auth-shell">
        <AmbientBackground shouldReduceMotion={shouldReduceMotion} />
      </main>
    );
  }

  if (auth.auth_required && !auth.authenticated) {
    return (
      <main className="app workspace-shell auth-shell">
        <AmbientBackground shouldReduceMotion={shouldReduceMotion} />
        <LoginPage error={authError} onLogin={handleLogin} />
      </main>
    );
  }

  return (
    <main className={`app workspace-shell active-tab-${tab}`}>
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
                  {tab === item.key && (
                    <motion.span className="nav-active-pill" layoutId="nav-active-pill" />
                  )}
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
        {auth.auth_required && (
          <button
            className="nav-item logout-item"
            type="button"
            onClick={() => void handleLogout()}
          >
            <LogOut size={16} />
            退出
          </button>
        )}
      </aside>
      <section className="main workspace-main">
        <div className="content">
          <div className="page-motion">
            {tab === "dashboard" && <DashboardPage />}
            {tab === "wechat" && <WechatPage />}
            {tab === "organize" && <OrganizePage />}
            {tab === "industry-chain" && <IndustryChainPage />}
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

function readInitialTab(): TabKey {
  if (typeof window === "undefined") {
    return "dashboard";
  }
  const urlTab = new URLSearchParams(window.location.search).get("tab");
  if (isTabKey(urlTab)) {
    return urlTab;
  }
  try {
    const storedTab = window.localStorage.getItem(TAB_STORAGE_KEY);
    if (isTabKey(storedTab)) {
      return storedTab;
    }
  } catch {
    // Safari 隐私模式或存储异常时退回默认页，不影响看板可用性。
  }
  return "dashboard";
}

function persistActiveTab(tab: TabKey) {
  try {
    window.localStorage.setItem(TAB_STORAGE_KEY, tab);
  } catch {
    // localStorage 不可用时仍保持 URL 可恢复。
  }
  const url = new URL(window.location.href);
  if (url.searchParams.get("tab") === tab) {
    return;
  }
  url.searchParams.set("tab", tab);
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function isTabKey(value: string | null): value is TabKey {
  return value !== null && TAB_KEYS.has(value as TabKey);
}
