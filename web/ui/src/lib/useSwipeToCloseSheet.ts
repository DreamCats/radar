import { useMemo, useRef, type TouchEventHandler } from "react";

const MOBILE_SHEET_QUERY = "(max-width: 760px)";
const INTERACTIVE_SELECTOR = "button, a, input, textarea, select, label, [role='button'], [data-swipe-close-ignore]";

type SwipeState = {
  startX: number;
  startY: number;
  lastX: number;
  lastY: number;
};

type SwipeToCloseOptions = {
  enabled?: boolean;
  mediaQuery?: string;
  minDistance?: number;
  verticalDominance?: number;
};

export function useSwipeToCloseSheet(onClose: () => void, options: SwipeToCloseOptions = {}) {
  const {
    enabled = true,
    mediaQuery = MOBILE_SHEET_QUERY,
    minDistance = 72,
    verticalDominance = 1.25,
  } = options;
  const stateRef = useRef<SwipeState | null>(null);

  return useMemo(
    () => ({
      "data-swipe-close-sheet": "true",
      onTouchStart: ((event) => {
        if (!enabled || event.touches.length !== 1 || !matchesMediaQuery(mediaQuery)) {
          stateRef.current = null;
          return;
        }
        if (isInteractiveTarget(event.target)) {
          stateRef.current = null;
          return;
        }
        const touch = event.touches[0];
        stateRef.current = {
          startX: touch.clientX,
          startY: touch.clientY,
          lastX: touch.clientX,
          lastY: touch.clientY,
        };
      }) satisfies TouchEventHandler<HTMLElement>,
      onTouchMove: ((event) => {
        const state = stateRef.current;
        if (!state || event.touches.length !== 1) {
          return;
        }
        const touch = event.touches[0];
        state.lastX = touch.clientX;
        state.lastY = touch.clientY;

        const deltaX = state.lastX - state.startX;
        const deltaY = state.lastY - state.startY;
        if (Math.abs(deltaX) > Math.abs(deltaY) * verticalDominance && Math.abs(deltaX) > 18) {
          stateRef.current = null;
          return;
        }
        if (deltaY > 8 && event.cancelable) {
          event.preventDefault();
        }
      }) satisfies TouchEventHandler<HTMLElement>,
      onTouchEnd: ((event) => {
        const state = stateRef.current;
        stateRef.current = null;
        if (!state) {
          return;
        }
        const touch = event.changedTouches[0];
        const endX = touch?.clientX ?? state.lastX;
        const endY = touch?.clientY ?? state.lastY;
        const deltaX = endX - state.startX;
        const deltaY = endY - state.startY;
        if (deltaY >= minDistance && deltaY > Math.abs(deltaX) * verticalDominance) {
          onClose();
        }
      }) satisfies TouchEventHandler<HTMLElement>,
      onTouchCancel: (() => {
        stateRef.current = null;
      }) satisfies TouchEventHandler<HTMLElement>,
    }),
    [enabled, mediaQuery, minDistance, onClose, verticalDominance],
  );
}

function matchesMediaQuery(query: string): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia(query).matches;
}

function isInteractiveTarget(target: EventTarget): boolean {
  return target instanceof Element && Boolean(target.closest(INTERACTIVE_SELECTOR));
}
