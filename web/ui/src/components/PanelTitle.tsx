import type { ReactNode } from "react";

export function PanelTitle(props: { title: string; meta?: string; children?: ReactNode }) {
  return (
    <div className="panel-title">
      <div>
        <h2>{props.title}</h2>
        {props.meta && <p>{props.meta}</p>}
      </div>
      {props.children}
    </div>
  );
}
