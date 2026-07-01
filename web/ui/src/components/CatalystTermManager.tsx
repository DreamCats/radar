import { GripVertical, Plus, RotateCcw, Save, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

import { useEscapeToClose } from "../lib/useEscapeToClose";
import { useSwipeToCloseSheet } from "../lib/useSwipeToCloseSheet";
import type { CatalystCategory, CatalystTermLibrary } from "../types";

type TermInputs = Record<string, string>;
type DraggingTerm = { categoryId: string; term: string };
type TermPlacement = "before" | "after";

export function CatalystTermManager(props: {
  library: CatalystTermLibrary;
  saving: boolean;
  onClose: () => void;
  onReset: () => Promise<void>;
  onSave: (library: CatalystTermLibrary) => Promise<void>;
}) {
  const [draft, setDraft] = useState<CatalystTermLibrary>(() => cloneLibrary(props.library));
  const [termInputs, setTermInputs] = useState<TermInputs>({});
  const [draggingTerm, setDraggingTerm] = useState<DraggingTerm | null>(null);
  const draggingTermRef = useRef<DraggingTerm | null>(null);
  const swipeClose = useSwipeToCloseSheet(props.onClose);
  useEscapeToClose(props.onClose);
  const totalTerms = useMemo(
    () => draft.categories.reduce((total, category) => total + category.terms.length, 0),
    [draft.categories],
  );

  useEffect(() => {
    function clearDraggingTerm() {
      draggingTermRef.current = null;
      setDraggingTerm(null);
    }

    window.addEventListener("pointerup", clearDraggingTerm);
    window.addEventListener("pointercancel", clearDraggingTerm);
    return () => {
      window.removeEventListener("pointerup", clearDraggingTerm);
      window.removeEventListener("pointercancel", clearDraggingTerm);
    };
  }, []);

  function updateCategory(categoryId: string, patch: Partial<CatalystCategory>) {
    setDraft((current) => ({
      ...current,
      categories: current.categories.map((category) =>
        category.id === categoryId ? { ...category, ...patch } : category,
      ),
    }));
  }

  function addCategory() {
    const id = `custom_${Date.now().toString(36)}`;
    setDraft((current) => ({
      ...current,
      categories: [
        ...current.categories,
        {
          id,
          name: "新标签",
          color: "#5e6ad2",
          terms: [],
        },
      ],
    }));
  }

  function removeCategory(categoryId: string) {
    setDraft((current) => ({
      ...current,
      categories: current.categories.filter((category) => category.id !== categoryId),
    }));
  }

  function addTerm(categoryId: string) {
    const value = (termInputs[categoryId] ?? "").trim();
    if (!value) {
      return;
    }
    setDraft((current) => ({
      ...current,
      categories: current.categories.map((category) => {
        if (category.id !== categoryId || category.terms.includes(value)) {
          return category;
        }
        return { ...category, terms: [...category.terms, value] };
      }),
    }));
    setTermInputs((current) => ({ ...current, [categoryId]: "" }));
  }

  function removeTerm(categoryId: string, term: string) {
    setDraft((current) => ({
      ...current,
      categories: current.categories.map((category) =>
        category.id === categoryId
          ? { ...category, terms: category.terms.filter((item) => item !== term) }
          : category,
      ),
    }));
  }

  function moveTerm(categoryId: string, movingTerm: string, targetTerm: string, placement: TermPlacement) {
    if (movingTerm === targetTerm) {
      return;
    }
    setDraft((current) => ({
      ...current,
      categories: current.categories.map((category) => {
        if (category.id !== categoryId) {
          return category;
        }
        const withoutMovingTerm = category.terms.filter((term) => term !== movingTerm);
        if (withoutMovingTerm.length === category.terms.length) {
          return category;
        }
        const targetIndex = withoutMovingTerm.indexOf(targetTerm);
        if (targetIndex === -1) {
          return category;
        }
        const nextTerms = [...withoutMovingTerm];
        nextTerms.splice(placement === "after" ? targetIndex + 1 : targetIndex, 0, movingTerm);
        if (sameTerms(nextTerms, category.terms)) {
          return category;
        }
        return { ...category, terms: nextTerms };
      }),
    }));
  }

  function startTermDrag(
    event: ReactPointerEvent<HTMLButtonElement>,
    categoryId: string,
    term: string,
  ) {
    if (event.pointerType === "mouse" && event.button !== 0) {
      return;
    }
    const nextDraggingTerm = { categoryId, term };
    draggingTermRef.current = nextDraggingTerm;
    setDraggingTerm(nextDraggingTerm);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
    event.stopPropagation();
  }

  function updateTermDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    const activeTerm = draggingTermRef.current;
    if (!activeTerm) {
      return;
    }
    const target = document
      .elementFromPoint(event.clientX, event.clientY)
      ?.closest<HTMLElement>("[data-catalyst-term]");
    const targetCategoryId = target?.dataset.categoryId;
    const targetTerm = target?.dataset.termValue;
    if (targetCategoryId !== activeTerm.categoryId || !targetTerm || targetTerm === activeTerm.term) {
      return;
    }
    const rect = target.getBoundingClientRect();
    const placement = event.clientX >= rect.left + rect.width / 2 ? "after" : "before";
    moveTerm(activeTerm.categoryId, activeTerm.term, targetTerm, placement);
    event.preventDefault();
  }

  function stopTermDrag() {
    draggingTermRef.current = null;
    setDraggingTerm(null);
  }

  return (
    <div className="catalyst-manager-backdrop" role="presentation" onMouseDown={props.onClose}>
      <section
        className="catalyst-manager panel"
        role="dialog"
        aria-modal="true"
        aria-label="催化词词库管理"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="catalyst-manager-head" {...swipeClose}>
          <div>
            <h2>词库管理</h2>
            <span>{draft.categories.length} 个标签 · {totalTerms} 个词</span>
          </div>
          <button className="mini-button" type="button" onClick={props.onClose} aria-label="关闭">
            <X size={15} />
          </button>
        </header>

        <div className="catalyst-manager-body">
          {draft.categories.map((category) => (
            <article className="catalyst-term-editor" key={category.id}>
              <div className="catalyst-term-editor-head">
                <input
                  className="catalyst-color-input"
                  type="color"
                  value={category.color}
                  aria-label={`${category.name} 颜色`}
                  onChange={(event) => updateCategory(category.id, { color: event.target.value })}
                />
                <input
                  className="catalyst-name-input"
                  value={category.name}
                  onChange={(event) => updateCategory(category.id, { name: event.target.value })}
                />
                <button
                  className="mini-button danger"
                  type="button"
                  onClick={() => removeCategory(category.id)}
                  aria-label={`删除${category.name}`}
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="catalyst-term-list" role="list">
                {category.terms.map((term) => (
                  <span
                    className={
                      draggingTerm?.categoryId === category.id && draggingTerm.term === term
                        ? "catalyst-term-pill dragging"
                        : "catalyst-term-pill"
                    }
                    data-catalyst-term
                    data-category-id={category.id}
                    data-term-value={term}
                    key={term}
                    role="listitem"
                  >
                    <button
                      className="catalyst-term-drag"
                      type="button"
                      aria-label={`拖动${term}排序`}
                      title="拖动排序"
                      onPointerDown={(event) => startTermDrag(event, category.id, term)}
                      onPointerMove={updateTermDrag}
                      onPointerUp={stopTermDrag}
                      onPointerCancel={stopTermDrag}
                    >
                      <GripVertical size={12} />
                    </button>
                    <span className="catalyst-term-label">{term}</span>
                    <button
                      className="catalyst-term-remove"
                      type="button"
                      onClick={() => removeTerm(category.id, term)}
                      aria-label={`删除${term}`}
                      title="删除关键词"
                    >
                      <X size={12} />
                    </button>
                  </span>
                ))}
              </div>
              <div className="catalyst-term-add">
                <input
                  value={termInputs[category.id] ?? ""}
                  placeholder="添加关键词"
                  onChange={(event) =>
                    setTermInputs((current) => ({ ...current, [category.id]: event.target.value }))
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      addTerm(category.id);
                    }
                  }}
                />
                <button className="mini-button" type="button" onClick={() => addTerm(category.id)}>
                  <Plus size={14} />
                </button>
              </div>
            </article>
          ))}
        </div>

        <footer className="catalyst-manager-foot">
          <button className="btn btn-sm" type="button" onClick={addCategory}>
            <Plus size={14} />
            新标签
          </button>
          <div>
            <button className="btn btn-sm" type="button" disabled={props.saving} onClick={() => void props.onReset()}>
              <RotateCcw size={14} />
              恢复默认
            </button>
            <button
              className="btn btn-primary btn-sm"
              type="button"
              disabled={props.saving}
              onClick={() => void props.onSave(draft)}
            >
              <Save size={14} />
              {props.saving ? "保存中" : "保存"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}

function cloneLibrary(library: CatalystTermLibrary): CatalystTermLibrary {
  return {
    version: library.version,
    categories: library.categories.map((category) => ({
      ...category,
      terms: [...category.terms],
    })),
  };
}

function sameTerms(left: string[], right: string[]) {
  return left.length === right.length && left.every((term, index) => term === right[index]);
}
