import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";
import "./motion.css";
import "./chat.css";
import "./chat-composer.css";
import "./chat-history.css";
import "./chat-markdown.css";
import "./dashboard.css";
import "./ambient.css";
import "./ingest.css";
import "./job-center.css";
import "./leaderboard.css";
import "./leaderboard-motion.css";
import "./leaderboard-responsive.css";
import "./loading.css";
import "./organize.css";
import "./organize-responsive.css";
import "./strategy-evidence-chain.css";
import "./strategy-evidence-detail.css";
import "./strategy-evidence-theme-quality.css";
import "./strategy-stock-chart.css";
import "./strategy-stock-drawer.css";
import "./wechat.css";

createRoot(document.getElementById("root")!).render(<App />);
