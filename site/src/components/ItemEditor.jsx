import React, { useState } from "react";

const QA = ["extracted", "reviewed", "approved"];
const MODES = ["SS", "SA", "BF", "FA"];
// rendered by dedicated controls above the generic field list
const HANDLED = new Set(["description"]);

export default function ItemEditor({ item, bookTitle, pdfAvailable, pdfHref, onSave }) {
  const [draft, setDraft] = useState(() => structuredClone(item));

  const setSystem = (field, value) => setDraft((d) => ({ ...d, system: { ...d.system, [field]: value } }));

  function renderField(field, value) {
    if (field === "modes" && value && typeof value === "object") {
      return (
        <span className="mode-row">
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
        <span className="ar-row">
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

  const imgSrc = draft.img && !/^(icons|systems|modules)\//.test(draft.img) ? `/assets/${draft.img}` : null;
  // an extracted book render may exist even when a library icon is assigned
  const renderPath = `${draft.meta?.book}/${draft.id}.png`;

  return (
    <div className="editor">
      <div className="editor-head">
        <h2>{draft.name}</h2>
        <div className="ref-line">
          <span className="ref-book">{bookTitle} — p. {draft.meta?.page}</span>
          <span className="ref-id">{draft.id}</span>
        </div>
      </div>

      <label>
        Name <input type="text" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </label>

      <label>
        QA status
        <select
          className={`qa-select qa-${draft.meta.qaStatus}`}
          value={draft.meta.qaStatus}
          onChange={(e) => setDraft({ ...draft, meta: { ...draft.meta, qaStatus: e.target.value } })}
        >
          {QA.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>

      <label className="block">
        Description
        <textarea
          rows={4}
          value={draft.system.description ?? ""}
          placeholder="Flavor text / rules summary for the Foundry sheet…"
          onChange={(e) => setSystem("description", e.target.value)}
        />
      </label>

      <label className="block">
        Image
        <input
          type="text"
          value={draft.img ?? ""}
          placeholder="corebook/example.webp (in data/_assets/) or icons/svg/…"
          onChange={(e) => {
            const img = e.target.value;
            setDraft((d) => {
              const next = { ...d };
              if (img) next.img = img;
              else delete next.img;
              return next;
            });
          }}
        />
      </label>
      <div className="art-row">
        {imgSrc && (
          <figure>
            <img className="img-preview" src={imgSrc} alt="" onError={(e) => (e.target.parentElement.style.display = "none")} />
            <figcaption>assigned</figcaption>
          </figure>
        )}
        {renderPath !== draft.img && (
          <figure>
            <img
              className="img-preview"
              src={`/assets/${renderPath}`}
              alt=""
              onError={(e) => (e.target.parentElement.style.display = "none")}
            />
            <figcaption>
              book render{" "}
              <button
                className="mini"
                onClick={() => setDraft((d) => ({ ...d, img: renderPath }))}
                title="Use the extracted book render as this item's image"
              >
                use
              </button>
            </figcaption>
          </figure>
        )}
      </div>

      <div className="field-grid">
        {Object.entries(draft.system)
          .filter(([field]) => !HANDLED.has(field))
          .map(([field, value]) => (
            <label key={field}>
              <span className="field-name">{field}</span> {renderField(field, value)}
            </label>
          ))}
      </div>

      <div className="editor-actions">
        <button className="primary" onClick={() => onSave(draft)}>Save</button>
        {pdfHref && (
          <button
            className="ghost"
            disabled={!pdfAvailable}
            title={pdfAvailable ? `Open ${bookTitle} at page ${draft.meta?.page}` : "Add the PDF path to data/books.json"}
            onClick={() => window.open(pdfHref, "sr6pdf", "width=980,height=1200,left=120,top=40")}
          >
            Open PDF · p. {draft.meta?.page}
          </button>
        )}
      </div>
    </div>
  );
}
