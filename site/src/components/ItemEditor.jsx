import React, { useEffect, useState } from "react";
import IconPicker from "./IconPicker.jsx";
import BookImages from "./BookImages.jsx";
import { prettyType } from "../labels.js";

const QA = ["extracted", "reviewed", "approved"];
const MODES = ["SS", "SA", "BF", "FA"];
// rendered by dedicated controls above the generic field list
const HANDLED = new Set(["description"]);

export default function ItemEditor({ item, bookTitle, books = {}, categoryName, pdfAvailable, pdfHref, onSave, onDelete, onAssignIcon, onAssignRender }) {
  const [draft, setDraft] = useState(() => structuredClone(item));
  const [picking, setPicking] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [renderExists, setRenderExists] = useState(true);

  // an icon assignment persists a new img for the SAME item id; React reuses
  // this component (key unchanged), so pull the fresh img/render into the draft
  // when the item prop changes, or the newly-set art wouldn't appear.
  useEffect(() => {
    setDraft((d) => ({ ...d, img: item.img }));
    setRenderExists(true);
  }, [item.img, item.id]);

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

  // the icon slot shows ONLY icon-library art (the loaded icon sets under
  // iconsets/, a shared generic/ icon, or a per-item <book>/lib/ pick); a
  // PDF-extracted render must never appear here — it belongs to the book-render
  // slot below, which loads <book>/<id>.png directly.
  const isIconAsset = draft.img && (
    draft.img.startsWith("iconsets/") || draft.img.startsWith("generic/") || draft.img.includes("/lib/")
  );
  const imgSrc = isIconAsset ? `/assets/${draft.img}` : null;
  const renderPath = `${draft.meta?.book}/${draft.id}.png`;

  return (
    <div className="editor">
      <div className="editor-head">
        <h2>{draft.name}</h2>
        <div className="ref-line">
          <span className="ref-book">
            {(draft.meta?.sources?.length
              ? draft.meta.sources
              : [{ book: draft.meta?.book, page: draft.meta?.page }]
            )
              .map((s, i) => `${i === 0 ? bookTitle : books[s.book]?.title ?? s.book} — p. ${s.page}`)
              .join(" · ")}
          </span>
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
        <figure>
          {imgSrc && draft.img !== renderPath ? (
            <img
              className="img-preview clickable"
              src={imgSrc}
              alt=""
              title="Click to choose a different icon"
              onClick={() => setPicking(true)}
              onError={(e) => {
                e.target.replaceWith(Object.assign(document.createElement("div"), { className: "img-empty", textContent: "—" }));
              }}
            />
          ) : (
            <div className="img-empty clickable" title="Click to choose an icon" onClick={() => setPicking(true)}>
              {draft.img === renderPath ? "—" : "none"}
            </div>
          )}
          <figcaption>icon</figcaption>
        </figure>
        <figure>
          {renderExists ? (
            <img
              className={`img-preview ${draft.img === renderPath ? "" : "clickable"}`}
              src={`/assets/${renderPath}`}
              alt=""
              title={draft.img === renderPath ? "Assigned" : "Click to use the book render"}
              onClick={() => draft.img !== renderPath && setDraft((d) => ({ ...d, img: renderPath }))}
              onError={() => setRenderExists(false)}
            />
          ) : (
            <div className="img-empty">none</div>
          )}
          <figcaption>
            book render{draft.img === renderPath ? " (assigned)" : ""}
          </figcaption>
        </figure>
        <div className="art-actions">
          <button className="ghost" onClick={() => setPicking(true)}>Choose icon…</button>
          <button className="ghost" onClick={() => setBrowsing(true)}>Book graphics…</button>
        </div>
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

      {picking && (
        <IconPicker
          item={draft}
          scopeLabel={`${draft.system.type ?? ""}${draft.system.subtype ? " · " + draft.system.subtype : ""}`}
          onAssign={(hit, mode) => onAssignIcon(draft, hit, mode)}
          onClose={() => setPicking(false)}
        />
      )}

      {browsing && (
        <BookImages
          book={draft.meta?.book}
          onPick={(path) => { onAssignRender(draft, path); setBrowsing(false); }}
          onClose={() => setBrowsing(false)}
        />
      )}

      <div className="editor-actions">
        <button className="primary" onClick={() => onSave(draft)}>Save</button>
        <button
          className="ghost danger"
          title="Delete this item from the library"
          onClick={() => {
            if (window.confirm(`Delete "${draft.name}"? This removes it from the library.`)) onDelete(draft);
          }}
        >
          Delete
        </button>
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
