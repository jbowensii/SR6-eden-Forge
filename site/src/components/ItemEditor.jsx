import React, { useEffect, useState } from "react";
import IconPicker from "./IconPicker.jsx";
import BookImages from "./BookImages.jsx";
import ArtSearch from "./ArtSearch.jsx";
import { prettyType } from "../labels.js";
import { EDEN, edenFields, missingRequired, isBlank } from "../../shared/edenSpec.mjs";

const QA = ["extracted", "reviewed", "approved"];
const MODES = ["SS", "SA", "BF", "FA"];
// rendered by dedicated controls above the generic field list
const HANDLED = new Set(["description"]);
// string fields that hold lists/prose and want a textarea, not a single line
const LONG_FIELDS = new Set([
  "activeSkills", "knowledgeSkills", "qualities", "spells", "gear", "weapons",
  "powers", "optionalPowers", "skills", "specializations", "gameEffect",
  "effect", "attacks", "contacts", "cyberware", "bioware", "augmentations",
]);

export default function ItemEditor({ item, domain, bookTitle, books = {}, categoryName, pdfAvailable, pdfHref, onSave, onDelete, onAssignIcon, onAssignRender }) {
  const [draft, setDraft] = useState(() => structuredClone(item));
  const [picking, setPicking] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [searchingArt, setSearchingArt] = useState(false);
  const [renderExists, setRenderExists] = useState(true);

  // an icon assignment persists a new img for the SAME item id; React reuses
  // this component (key unchanged), so pull the fresh img/render into the draft
  // when the item prop changes, or the newly-set art wouldn't appear.
  useEffect(() => {
    setDraft((d) => ({ ...d, img: item.img }));
    setRenderExists(true);
  }, [item.img, item.id]);

  const setSystem = (field, value) => setDraft((d) => ({ ...d, system: { ...d.system, [field]: value } }));

  // Pasting book text carries hard line breaks from the PDF columns; collapse
  // CRs/newlines to single spaces so descriptions stay one clean paragraph.
  const pasteClean = (e, current, commit) => {
    const text = e.clipboardData?.getData("text") ?? "";
    if (!/[\r\n]/.test(text)) return;                 // nothing to fix
    e.preventDefault();
    const el = e.target;
    const clean = text.replace(/[\r\n]+/g, " ").replace(/[ \t]{2,}/g, " ").trim();
    const s = el.selectionStart ?? current.length;
    const en = el.selectionEnd ?? current.length;
    commit(current.slice(0, s) + clean + current.slice(en));
  };

  // Eden export readiness for this item's domain: which Foundry type it becomes,
  // which fields Eden recognizes, and which required ones are still blank.
  const dom = domain ?? item._domain;
  const spec = EDEN[dom] ?? null;
  const edenSet = edenFields(dom);
  const missing = spec ? missingRequired(dom, draft.system) : [];
  const reqTotal = spec ? spec.req.length : 0;
  const reqSet = reqTotal - missing.length;
  // required Eden fields entirely absent from the system block — offer to add
  const absentReq = spec ? spec.req.filter((f) => !(f in draft.system)) : [];
  const addMissingEden = () =>
    setDraft((d) => {
      const next = { ...d.system };
      for (const f of absentReq) if (!(f in next)) next[f] = "";
      return { ...d, system: next };
    });

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
      // long, prose-y, or list fields get a textarea; short ones an input
      if (value.length > 48 || LONG_FIELDS.has(field)) {
        return (
          <textarea rows={Math.min(8, Math.ceil((value.length || 1) / 48) + 1)}
            value={value} onChange={(e) => setSystem(field, e.target.value)}
            onPaste={(e) => pasteClean(e, value, (v) => setSystem(field, v))} />
        );
      }
      return <input type="text" value={value} onChange={(e) => setSystem(field, e.target.value)} />;
    }
    // a nested object (e.g. an actor's attributes) -> a labelled sub-field grid
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return (
        <span className="obj-grid">
          {Object.entries(value).map(([k, v]) => (
            <label key={k} className="obj-cell">
              <span className="obj-key">{k}</span>
              <input
                type={typeof v === "number" ? "number" : "text"}
                value={v}
                onChange={(e) => {
                  const nv = typeof v === "number" ? Number(e.target.value) : e.target.value;
                  setSystem(field, { ...value, [k]: nv });
                }}
              />
            </label>
          ))}
        </span>
      );
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

      {spec && (
        <div className={`eden-panel ${missing.length ? "needs" : "ready"}`}>
          <div className="eden-head">
            <span className="eden-type" title="shadowrun6-eden Foundry document type">
              Eden{spec.actor ? " actor" : ""} → <code>{spec.type}</code>
            </span>
            <span className={`eden-status ${missing.length ? "needs" : "ready"}`}>
              {reqTotal === 0
                ? (missing.length ? "" : "no required fields")
                : `${reqSet}/${reqTotal} required set`}
              {missing.length === 0 && " ✓"}
            </span>
          </div>
          {draft.system?.type && (
            <div className="eden-codes" title="Adopted Eden type/subtype (raw Commlink6 code shown at right)">
              <code>{draft.system.type}{draft.system.subtype ? ` / ${draft.system.subtype}` : ""}</code>
              {draft.system?._cl6?.attrs && (
                <span className="eden-src">← cl6 {draft.system._cl6.attrs.type || "?"}
                  {draft.system._cl6.attrs.subtype ? `/${draft.system._cl6.attrs.subtype}` : ""}</span>
              )}
            </div>
          )}
          {missing.length > 0 && (
            <div className="eden-missing">
              Needs: {missing.map((f) => <code key={f} className="miss">{f}</code>)}
              {absentReq.length > 0 && (
                <button className="ghost tiny" onClick={addMissingEden} title="Add blank fields so you can fill them">
                  + add {absentReq.length} field{absentReq.length > 1 ? "s" : ""}
                </button>
              )}
            </div>
          )}
        </div>
      )}

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
          onPaste={(e) => pasteClean(e, draft.system.description ?? "", (v) => setSystem("description", v))}
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
          <button className="ghost" onClick={() => setSearchingArt(true)} title="Search the web for artwork">Find art…</button>
        </div>
      </div>

      <div className="field-grid">
        {Object.entries(draft.system)
          .filter(([field]) => !HANDLED.has(field))
          .map(([field, value]) => {
            const isEden = edenSet.has(field);
            const isReq = spec?.req.includes(field);
            const blankReq = isReq && isBlank(value);
            return (
              <label key={field} className={`${isEden ? "eden-field" : "extra-field"}${blankReq ? " blank-req" : ""}`}>
                <span className="field-name">
                  {field}
                  {isEden && <span className={`eden-tag ${isReq ? "req" : ""}`} title={isReq ? "Eden required field" : "Eden field"}>eden{isReq ? "*" : ""}</span>}
                </span> {renderField(field, value)}
              </label>
            );
          })}
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

      {searchingArt && (
        <ArtSearch
          item={draft}
          onAssigned={(img) => setDraft((d) => ({ ...d, img }))}
          onClose={() => setSearchingArt(false)}
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
