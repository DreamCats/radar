import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";
import "./motion.css";
import "./dashboard.css";
import "./ingest.css";
import "./job-center.css";
import "./leaderboard.css";
import "./messages.css";
import "./organize.css";
import "./organize-aggregate.css";
import "./organize-responsive.css";
import "./wechat.css";

createRoot(document.getElementById("root")!).render(<App />);
