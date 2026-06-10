import type { ReactNode } from "react";

export function PanelTitle(props: { title: string; meta?: string; titleExtra?: ReactNode; children?: ReactNode }) {
  return (
    <div className="panel-title">
      <div>
        <div className="panel-title-heading">
          <h2>{props.title}</h2>
          {props.titleExtra}
        </div>
        {props.meta && <p>{props.meta}</p>}
      </div>
      {props.children}
    </div>
  );
}
