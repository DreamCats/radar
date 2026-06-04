import { useState } from "react";

import { TabButton } from "./components/TabButton";
import { IngestPage } from "./pages/IngestPage";
import { MessagesPage } from "./pages/MessagesPage";
import { RunsPage } from "./pages/RunsPage";

type TabKey = "messages" | "runs" | "ingest";

export function App() {
  const [tab, setTab] = useState<TabKey>("messages");

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">radar dashboard</p>
          <h1>原数据工作台</h1>
        </div>
        <nav className="tabs" aria-label="dashboard sections">
          <TabButton active={tab === "messages"} onClick={() => setTab("messages")}>
            消息
          </TabButton>
          <TabButton active={tab === "runs"} onClick={() => setTab("runs")}>
            运行
          </TabButton>
          <TabButton active={tab === "ingest"} onClick={() => setTab("ingest")}>
            拉取
          </TabButton>
        </nav>
      </header>
      {tab === "messages" && <MessagesPage />}
      {tab === "runs" && <RunsPage />}
      {tab === "ingest" && <IngestPage />}
    </main>
  );
}
