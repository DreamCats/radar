import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";
import "@xyflow/react/dist/style.css";
import "./motion.css";
import "./chat.css";
import "./chat-composer.css";
import "./chat-history.css";
import "./chat-markdown.css";
import "./ambient.css";
import "./analyst.css";
import "./ingest.css";
import "./job-center.css";
import "./industry-chain.css";
import "./industry-chain-flow.css";
import "./industry-chain-detail.css";
import "./industry-chain-mobile-article.css";
import "./login.css";
import "./loading.css";
import "./schedule.css";
import "./wechat.css";

createRoot(document.getElementById("root")!).render(<App />);
