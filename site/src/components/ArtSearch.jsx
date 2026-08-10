import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { artSearch, artDownload } from "../api.js";

// Search the internet for artwork (Shadowrun/cyberpunk + item name) and assign a
// pick to the item's art (render) slot. This game has decades of art out there.
export default function ArtSearch({ item, onAssigned, onClose }) {
  // The name alone is not a search. "Ares Predator VI" against a general image
  // index returns fitness programmes; the words that say what the thing IS have
  // to go in with it. Subtype beats type ("PISTOLS_HEAVY" -> "pistols heavy"),
  // and the user can still edit the box before searching.
  const context = (item?.system?.subtype || item?.system?.type || "")
    .toLowerCase().replace(/_/g, " ").trim();
  const [q, setQ] = useState([item?.name, context].filter(Boolean).join(" "));
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("");
  const [searchUrl, setSearchUrl] = useState("");

  const run = async () => {
    setStatus("searching…"); setResults([]);
    try {
      const r = await artSearch(q);
      setResults(r.results ?? []);
      setSearchUrl(r.searchUrl ?? "");
      setStatus(r.results?.length ? "" : (r.error ? `no results (${r.error})` : "no results"));
    } catch (e) { setStatus(String(e.message ?? e)); }
  };
  useEffect(() => { if (item?.name) run(); /* eslint-disable-next-line */ }, [item?.id]);

  const pick = async (url) => {
    setStatus("downloading…");
    try {
      const r = await artDownload({ book: item._book, domain: item._domain, category: item._category, id: item.id, url });
      onAssigned?.(r.img);
      setStatus("assigned ✓");
      setTimeout(onClose, 500);
    } catch (e) { setStatus(`failed: ${e.message ?? e}`); }
  };

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal art-search" onClick={(e) => e.stopPropagation()}>
        <div className="setup-head">
          <h2>Find Artwork — {item?.name}</h2>
          <button className="ghost" onClick={onClose}>✕</button>
        </div>
        <div className="art-search-bar">
          <input value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()} placeholder="search terms" />
          <button className="primary" onClick={run}>Search</button>
          {searchUrl && <a className="ghost" href={searchUrl} target="_blank" rel="noreferrer">open in browser ↗</a>}
        </div>
        {status && <p className="setup-hint">{status}</p>}
        <div className="art-grid">
          {results.map((r, i) => (
            <button key={i} className="art-cell" title="Assign this artwork" onClick={() => pick(r.full)}>
              <img src={r.thumb} alt="" loading="lazy"
                onError={(e) => { e.target.closest(".art-cell").style.display = "none"; }} />
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
