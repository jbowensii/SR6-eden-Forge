import React, { useState } from "react";

const QA = ["extracted", "reviewed", "approved"];
const MODES = ["SS", "SA", "BF", "FA"];

export default function ItemEditor({ item, onSave }) {
  const [draft, setDraft] = useState(() => structuredClone(item));

  const setSystem = (field, value) => setDraft((d) => ({ ...d, system: { ...d.system, [field]: value } }));

  function renderField(field, value) {
    if (field === "modes" && value && typeof value === "object") {
      return (
        <span>
          {MODES.map((m) => (
            <label key={m} className="inline">
              <input type="checkbox" checked={!!value[m]} onChange={(e) => setSystem("modes", { ...value, [m]: e.target.checked })} />
              {m}
            </label>
          ))}
        </span>
      );
    }
    if (field === "attackRating" && Array.isArray(value)) {
      return (
        <span>
          {value.map((v, i) => (
            <input
              key={i}
              className="ar"
              type="number"
              value={v}
              onChange={(e) => {
                const next = [...value];
                next[i] = Number(e.target.value);
                setSystem("attackRating", next);
              }}
            />
          ))}
        </span>
      );
    }
    if (typeof value === "boolean") {
      return <input type="checkbox" checked={value} onChange={(e) => setSystem(field, e.target.checked)} />;
    }
    if (typeof value === "number") {
      return <input type="number" value={value} onChange={(e) => setSystem(field, Number(e.target.value))} />;
    }
    if (typeof value === "string") {
      return <input type="text" value={value} onChange={(e) => setSystem(field, e.target.value)} />;
    }
    return <code>{JSON.stringify(value)}</code>;
  }

  return (
    <div className="editor">
      <h2>{draft.id}</h2>
      <label>
        Name <input type="text" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </label>
      <label>
        QA status
        <select
          value={draft.meta.qaStatus}
          onChange={(e) => setDraft({ ...draft, meta: { ...draft.meta, qaStatus: e.target.value } })}
        >
          {QA.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      {Object.entries(draft.system).map(([field, value]) => (
        <label key={field}>
          {field} {renderField(field, value)}
        </label>
      ))}
      <button onClick={() => onSave(draft)}>Save</button>
    </div>
  );
}
