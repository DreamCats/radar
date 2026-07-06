import { useEffect, useState } from "react";
import {
  BarChart3,
  Database,
  FileText,
  LogOut,
  ListTodo,
  Menu,
  MessageCircle,
  Network,
  Radar,
  RadioTower,
  Tags,
  Timer,
  UserRoundCheck,
  X,
} from "lucide-react";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "motion/react";

import { AUTH_EXPIRED_EVENT, fetchAuthStatus, login, logout } from "./api/radarApi";
import { AnalystPage } from "./pages/AnalystPage";
import { CatalystPage } from "./pages/CatalystPage";
import { IngestPage } from "./pages/IngestPage";
import { IndustryChainPage } from "./pages/IndustryChainPage";
import { LoginPage } from "./pages/LoginPage";
import { PremarketPage } from "./pages/PremarketPage";
import { SchedulePage } from "./pages/SchedulePage";
import { TasksPage } from "./pages/TasksPage";
import { ValuationCluesPage } from "./pages/ValuationCluesPage";
import { WechatPage } from "./pages/WechatPage";
import type { AuthStatus } from "./types";

type TabKey =
  | "wechat"
  | "catalyst"
  | "valuation-clues"
  | "premarket"
  | "industry-chain"
  | "analyst"
  | "tasks"
  | "schedule"
  | "ingest";

const NAV_ITEMS = [
  { key: "wechat", label: "微信", icon: MessageCircle },
  { key: "catalyst", label: "催化词", icon: Tags },
  { key: "valuation-clues", label: "估值线索", icon: FileText },
  { key: "premarket", label: "盘前预测", icon: Radar },
  { key: "industry-chain", label: "产业链", icon: Network },
  { key: "analyst", label: "分析师", icon: UserRoundCheck },
  { key: "tasks", label: "任务", icon: ListTodo },
  { key: "schedule", label: "定时", icon: Timer },
  { key: "ingest", label: "入库", icon: Database },
] satisfies Array<{ key: TabKey; label: string; icon: typeof MessageCircle }>;
const HIDDEN_NAV_KEYS = new Set<TabKey>(["industry-chain"]);
const VISIBLE_NAV_ITEMS = NAV_ITEMS.filter((item) => !HIDDEN_NAV_KEYS.has(item.key));

const TAB_STORAGE_KEY = "radar.activeTab";
const TAB_KEYS = new Set<TabKey>(VISIBLE_NAV_ITEMS.map((item) => item.key));
const MOBILE_NAV_QUERY = "(max-width: 720px)";
const MOBILE_NAV_EDGE_WIDTH = 32;
const MOBILE_NAV_SWIPE_DISTANCE = 56;
const MOBILE_NAV_VERTICAL_TOLERANCE = 1.25;
const MOBILE_NAV_SWIPE_IGNORE_SELECTOR = ".chat-launcher-shell";

export function App() {
  const [tab, setTab] = useState<TabKey>(() => readInitialTab());
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const shouldReduceMotion = useReducedMotion();
  const activeItem = NAV_ITEMS.find((item) => item.key === tab) ?? NAV_ITEMS[0];
  const navGesturesEnabled = auth !== null && (!auth.auth_required || auth.authenticated);

  useMobileNavSwipe(navGesturesEnabled, mobileNavOpen, setMobileNavOpen);

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
    function handleAuthExpired() {
      setAuth({ auth_required: true, authenticated: false, username: null });
      setAuthError("密钥无效，请重新输入。");
      setMobileNavOpen(false);
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
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

  useEffect(() => {
    if (!mobileNavOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileNavOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen]);

  async function handleLogin(token: string) {
    const next = await login(token);
    setAuth(next);
    setAuthError(null);
  }

  async function handleLogout() {
    const next = await logout();
    setAuth(next);
    setTab("wechat");
  }

  function handleSelectTab(nextTab: TabKey) {
    setTab(nextTab);
    setMobileNavOpen(false);
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
      <MobileTopbar
        activeLabel={activeItem.label}
        menuOpen={mobileNavOpen}
        onToggleMenu={() => setMobileNavOpen((open) => !open)}
      />
      <WorkspaceSidebar
        authRequired={auth.auth_required}
        layoutId="workspace-nav"
        shouldReduceMotion={shouldReduceMotion}
        tab={tab}
        variant="desktop"
        onLogout={handleLogout}
        onSelectTab={handleSelectTab}
      />
      <AnimatePresence initial={false}>
        {mobileNavOpen && (
          <motion.button
            className="mobile-nav-scrim"
            key="mobile-nav-scrim"
            type="button"
            aria-label="关闭导航"
            onClick={() => setMobileNavOpen(false)}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={shouldReduceMotion ? { duration: 0.08 } : { duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          />
        )}
        {mobileNavOpen && (
          <WorkspaceSidebar
            authRequired={auth.auth_required}
            key="mobile-nav-sidebar"
            layoutId="workspace-mobile-nav"
            shouldReduceMotion={shouldReduceMotion}
            tab={tab}
            variant="mobile"
            onLogout={handleLogout}
            onSelectTab={handleSelectTab}
          />
        )}
      </AnimatePresence>
      <section className="main workspace-main">
        <div className="content">
          <div className="page-motion">
            {tab === "wechat" && <WechatPage />}
            {tab === "catalyst" && <CatalystPage />}
            {tab === "valuation-clues" && <ValuationCluesPage />}
            {tab === "premarket" && <PremarketPage />}
            {tab === "industry-chain" && <IndustryChainPage />}
            {tab === "analyst" && <AnalystPage />}
            {tab === "tasks" && <TasksPage />}
            {tab === "schedule" && <SchedulePage />}
            {tab === "ingest" && <IngestPage />}
          </div>
        </div>
      </section>
    </main>
  );
}

function MobileTopbar(props: {
  activeLabel: string;
  menuOpen: boolean;
  onToggleMenu: () => void;
}) {
  return (
    <header className="mobile-topbar">
      <button
        className="mobile-menu-button"
        type="button"
        aria-label={props.menuOpen ? "关闭导航" : "打开导航"}
        aria-expanded={props.menuOpen}
        onClick={props.onToggleMenu}
      >
        {props.menuOpen ? <X size={20} /> : <Menu size={20} />}
      </button>
      <div className="mobile-topbar-title">
        <span>radar</span>
        <strong>{props.activeLabel}</strong>
      </div>
    </header>
  );
}

function WorkspaceSidebar(props: {
  authRequired: boolean;
  layoutId: string;
  shouldReduceMotion: boolean | null;
  tab: TabKey;
  variant: "desktop" | "mobile";
  onLogout: () => Promise<void>;
  onSelectTab: (tab: TabKey) => void;
}) {
  const sidebarClass = props.variant === "mobile" ? "sidebar mobile-sidebar" : "sidebar desktop-sidebar";
  const navLabel = props.variant === "mobile" ? "移动端导航" : "workspace sections";
  const sidebarMotion = props.variant === "mobile" ? mobileSidebarMotion(props.shouldReduceMotion) : {};
  return (
    <motion.aside className={sidebarClass} {...sidebarMotion}>
      <div className="brand brand-block">
        <motion.span
          className="dot brand-dot"
          animate={props.shouldReduceMotion ? { opacity: 0.9 } : { opacity: [0.72, 1, 0.72], scale: [1, 1.16, 1] }}
          transition={props.shouldReduceMotion ? { duration: 0.12 } : { duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        />
        <span>radar</span>
      </div>
      <LayoutGroup id={props.layoutId}>
        <nav className="nav-group side-nav" aria-label={navLabel}>
          <div className="eyebrow">看板</div>
          {VISIBLE_NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <motion.button
                className={props.tab === item.key ? "nav-item active" : "nav-item"}
                key={item.key}
                type="button"
                onClick={() => props.onSelectTab(item.key)}
                whileHover={props.shouldReduceMotion ? undefined : { x: 2 }}
                whileTap={props.shouldReduceMotion ? undefined : { scale: 0.985 }}
              >
                {props.tab === item.key && (
                  <motion.span className="nav-active-pill" layoutId={`${props.layoutId}-active-pill`} />
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
      {props.authRequired && (
        <button
          className="nav-item logout-item"
          type="button"
          onClick={() => void props.onLogout()}
        >
          <LogOut size={16} />
          退出
        </button>
      )}
    </motion.aside>
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

function mobileSidebarMotion(shouldReduceMotion: boolean | null) {
  if (shouldReduceMotion) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.12 },
    };
  }
  return {
    initial: { opacity: 0.88, x: "-102%" },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0.88, x: "-102%" },
    transition: { type: "spring", stiffness: 430, damping: 38, mass: 0.9 },
  };
}

function useMobileNavSwipe(enabled: boolean, mobileNavOpen: boolean, setMobileNavOpen: (open: boolean) => void) {
  useEffect(() => {
    if (!enabled || typeof window === "undefined") {
      return;
    }

    let gesture: { startX: number; startY: number } | null = null;

    const isMobileNavLayout = () => window.matchMedia(MOBILE_NAV_QUERY).matches;

    const onTouchStart = (event: TouchEvent) => {
      if (!isMobileNavLayout() || event.touches.length !== 1) {
        gesture = null;
        return;
      }
      if (isMobileNavSwipeIgnored(event.target)) {
        gesture = null;
        return;
      }

      const touch = event.touches[0];
      if (!mobileNavOpen && touch.clientX > MOBILE_NAV_EDGE_WIDTH) {
        gesture = null;
        return;
      }

      gesture = { startX: touch.clientX, startY: touch.clientY };
    };

    const onTouchMove = (event: TouchEvent) => {
      if (!gesture || event.touches.length !== 1) {
        return;
      }

      const touch = event.touches[0];
      const deltaX = touch.clientX - gesture.startX;
      const deltaY = touch.clientY - gesture.startY;
      if (Math.abs(deltaY) > 12 && Math.abs(deltaY) > Math.abs(deltaX)) {
        gesture = null;
      }
    };

    const onTouchEnd = (event: TouchEvent) => {
      if (!gesture) {
        return;
      }

      const touch = event.changedTouches[0];
      const start = gesture;
      gesture = null;
      if (!touch) {
        return;
      }

      const deltaX = touch.clientX - start.startX;
      const deltaY = touch.clientY - start.startY;
      const isHorizontalSwipe = Math.abs(deltaX) > Math.abs(deltaY) * MOBILE_NAV_VERTICAL_TOLERANCE;
      if (!isHorizontalSwipe) {
        return;
      }

      if (!mobileNavOpen && deltaX >= MOBILE_NAV_SWIPE_DISTANCE) {
        setMobileNavOpen(true);
      }
      if (mobileNavOpen && deltaX <= -MOBILE_NAV_SWIPE_DISTANCE) {
        setMobileNavOpen(false);
      }
    };

    const onTouchCancel = () => {
      gesture = null;
    };

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    window.addEventListener("touchcancel", onTouchCancel, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
      window.removeEventListener("touchcancel", onTouchCancel);
    };
  }, [enabled, mobileNavOpen, setMobileNavOpen]);
}

function isMobileNavSwipeIgnored(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(MOBILE_NAV_SWIPE_IGNORE_SELECTOR));
}

function readInitialTab(): TabKey {
  if (typeof window === "undefined") {
    return "wechat";
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
    // Safari 隐私模式或存储异常时退回默认页，不影响主界面可用性。
  }
  return "wechat";
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
