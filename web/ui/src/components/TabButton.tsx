import type { ReactNode } from "react";

export function TabButton(props: { active: boolean; children: ReactNode; onClick: () => void }) {
  return (
    <button className={props.active ? "tab active" : "tab"} type="button" onClick={props.onClick}>
      {props.children}
    </button>
  );
}
