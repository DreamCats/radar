import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";
import "./motion.css";
import "./dashboard.css";
import "./ingest.css";
import "./messages.css";
import "./organize.css";
import "./organize-responsive.css";
import "./wechat.css";

createRoot(document.getElementById("root")!).render(<App />);
