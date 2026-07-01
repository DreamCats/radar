import { useEffect } from "react";

type EscapeToCloseOptions = {
  enabled?: boolean;
  ignoreWhenSelector?: string;
};

export function useEscapeToClose(onClose: () => void, options: EscapeToCloseOptions = {}) {
  const { enabled = true, ignoreWhenSelector } = options;

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.isComposing) {
        return;
      }
      if (ignoreWhenSelector && document.querySelector(ignoreWhenSelector)) {
        return;
      }
      event.preventDefault();
      onClose();
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled, ignoreWhenSelector, onClose]);
}
