import React, { useEffect, useState } from "react";

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

  return (
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
          {results.map((rel) => (
            <img
              key={rel}
              src={`/icon-lib/${rel}`}
              title={rel}
              className={selected === rel ? "selected" : ""}
              onClick={() => setSelected(rel)}
              loading="lazy"
            />
          ))}
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
    </div>
  );
}
