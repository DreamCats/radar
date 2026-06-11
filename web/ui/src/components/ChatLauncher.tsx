import { MessageCircle } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { createPortal } from "react-dom";

import { ChatWorkspace } from "./ChatWorkspace";
import type { ChatSurfaceProps } from "./chatTypes";
import { useChatController } from "./useChatController";

export type ChatLauncherProps = ChatSurfaceProps & {
  buttonLabel: string;
  buttonClassName?: string;
};

export function ChatLauncher(props: ChatLauncherProps) {
  const [open, setOpen] = useState(false);
  const controller = useChatController(props, open);

  function closeLauncher() {
    controller.stopStreaming();
    setOpen(false);
  }

  const overlay = (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="chat-launcher-shell"
          role="dialog"
          aria-modal="true"
          aria-label={props.title}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
        >
          <motion.button
            className="chat-launcher-scrim"
            type="button"
            aria-label="关闭对话"
            onClick={closeLauncher}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.aside
            className="chat-launcher-panel"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            <ChatWorkspace
              controller={controller}
              title={props.title}
              subtitle={props.subtitle}
              surface={props.surface}
              entityId={props.entityId}
              evidence={props.evidence}
              onClose={closeLauncher}
            />
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );

  return (
    <>
      <button className={props.buttonClassName ?? "btn btn-sm"} type="button" onClick={() => setOpen(true)}>
        <MessageCircle size={14} />
        {props.buttonLabel}
      </button>
      {createPortal(overlay, document.body)}
    </>
  );
}
