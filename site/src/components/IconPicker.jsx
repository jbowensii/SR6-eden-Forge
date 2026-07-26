import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";

export default function IconPicker({ item, subtype, onAssign, onClose }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      fetch(`/api/icons?q=${encodeURIComponent(q)}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("library not configured"))))
        .then(setResults)
        .catch((e) => setError(String(e.message ?? e)));
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  async function assign(mode) {
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    try {
      await onAssign(selected, mode);
      onClose();
    } catch (e) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  // the editor panel's clip-path creates a containing block that would trap
  // and clip a position:fixed overlay — render at document.body instead
  return createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Choose icon — {item.name}</h3>
          <button className="mini" onClick={onClose}>✕</button>
        </div>
        <input
          autoFocus
          type="text"
          placeholder="search the icon library… (e.g. pistol, drone, medkit)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="icon-grid">
          {results.map((hit) => {
            const key = `${hit.r}/${hit.p}`;
            return (
              <img
                key={key}
                src={`/icon-lib/${hit.r}/${hit.p}`}
                title={hit.p}
                className={selected && selected.r === hit.r && selected.p === hit.p ? "selected" : ""}
                onClick={() => setSelected(hit)}
                loading="lazy"
              />
            );
          })}
          {query && !results.length && <div className="icon-empty">no matches</div>}
        </div>
        {error && <div className="modal-error">{error}</div>}
        <div className="modal-actions">
          <button className="primary" disabled={!selected || busy} onClick={() => assign("item")}>
            Set for this item
          </button>
          <button className="ghost" disabled={!selected || busy} onClick={() => assign("generic")}>
            Set as generic for {subtype || "category"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
