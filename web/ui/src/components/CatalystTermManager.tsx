import { Plus, RotateCcw, Save, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { CatalystCategory, CatalystTermLibrary } from "../types";

type TermInputs = Record<string, string>;

export function CatalystTermManager(props: {
  library: CatalystTermLibrary;
  saving: boolean;
  onClose: () => void;
  onReset: () => Promise<void>;
  onSave: (library: CatalystTermLibrary) => Promise<void>;
}) {
  const [draft, setDraft] = useState<CatalystTermLibrary>(() => cloneLibrary(props.library));
  const [termInputs, setTermInputs] = useState<TermInputs>({});
  const totalTerms = useMemo(
    () => draft.categories.reduce((total, category) => total + category.terms.length, 0),
    [draft.categories],
  );

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

  return (
    <div className="catalyst-manager-backdrop" role="presentation" onMouseDown={props.onClose}>
      <section
        className="catalyst-manager panel"
        role="dialog"
        aria-modal="true"
        aria-label="催化词词库管理"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="catalyst-manager-head">
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
              <div className="catalyst-term-list">
                {category.terms.map((term) => (
                  <button
                    className="catalyst-term-pill"
                    key={term}
                    type="button"
                    onClick={() => removeTerm(category.id, term)}
                    title="点击删除"
                  >
                    {term}
                    <X size={12} />
                  </button>
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
