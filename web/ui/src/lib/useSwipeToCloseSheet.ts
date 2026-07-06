import { useMemo, useRef, type TouchEventHandler } from "react";

const MOBILE_SHEET_QUERY = "(max-width: 760px)";
const INTERACTIVE_SELECTOR = "button, a, input, textarea, select, label, [role='button'], [data-swipe-close-ignore]";
const HORIZONTAL_CANCEL_DISTANCE = 18;
const VERTICAL_CANCEL_DISTANCE = 18;
const PREVENT_SCROLL_DISTANCE = 8;

type SwipeState = {
  startX: number;
  startY: number;
  lastX: number;
  lastY: number;
};

type SwipeDirection = "down" | "right";

type SwipeToCloseOptions = {
  enabled?: boolean;
  direction?: SwipeDirection;
  mediaQuery?: string;
  minDistance?: number;
  startEdgeWidth?: number;
  verticalDominance?: number;
};

export function useSwipeToCloseSheet(onClose: () => void, options: SwipeToCloseOptions = {}) {
  const {
    enabled = true,
    direction = "down",
    mediaQuery = MOBILE_SHEET_QUERY,
    minDistance = 72,
    startEdgeWidth,
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
        if (direction === "right" && startEdgeWidth !== undefined && touch.clientX > startEdgeWidth) {
          stateRef.current = null;
          return;
        }
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
        if (shouldCancelSwipe(direction, deltaX, deltaY, verticalDominance)) {
          stateRef.current = null;
          return;
        }
        if (shouldPreventDefault(direction, deltaX, deltaY, verticalDominance) && event.cancelable) {
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
        if (isCloseSwipe(direction, deltaX, deltaY, minDistance, verticalDominance)) {
          onClose();
        }
      }) satisfies TouchEventHandler<HTMLElement>,
      onTouchCancel: (() => {
        stateRef.current = null;
      }) satisfies TouchEventHandler<HTMLElement>,
    }),
    [direction, enabled, mediaQuery, minDistance, onClose, startEdgeWidth, verticalDominance],
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

function shouldCancelSwipe(direction: SwipeDirection, deltaX: number, deltaY: number, verticalDominance: number): boolean {
  if (direction === "down") {
    return Math.abs(deltaX) > Math.abs(deltaY) * verticalDominance && Math.abs(deltaX) > HORIZONTAL_CANCEL_DISTANCE;
  }
  if (deltaX < -HORIZONTAL_CANCEL_DISTANCE) {
    return true;
  }
  return Math.abs(deltaY) > Math.abs(deltaX) * verticalDominance && Math.abs(deltaY) > VERTICAL_CANCEL_DISTANCE;
}

function shouldPreventDefault(direction: SwipeDirection, deltaX: number, deltaY: number, verticalDominance: number): boolean {
  if (direction === "down") {
    return deltaY > PREVENT_SCROLL_DISTANCE;
  }
  return deltaX > PREVENT_SCROLL_DISTANCE && Math.abs(deltaX) > Math.abs(deltaY) * verticalDominance;
}

function isCloseSwipe(
  direction: SwipeDirection,
  deltaX: number,
  deltaY: number,
  minDistance: number,
  verticalDominance: number,
): boolean {
  if (direction === "down") {
    return deltaY >= minDistance && deltaY > Math.abs(deltaX) * verticalDominance;
  }
  return deltaX >= minDistance && deltaX > Math.abs(deltaY) * verticalDominance;
}
