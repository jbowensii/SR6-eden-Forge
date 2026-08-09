import React, { useEffect, useState } from "react";
import { getDuplicates } from "../api.js";

/** Name-collisions, with the row that will survive and the ones that will go.
 *
 * Shown before anything is removed, and every row is listed rather than
 * counted. A delete aimed at the wrong twin leaves no trace to notice
 * afterwards — the evidence of the mistake is an absence.
 */
export default function Duplicates({ onClose, onRemove }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [skip, setSkip] = useState(() => new Set());   // groups the user unticked

  useEffect(() => {
    getDuplicates().then(setData).catch((e) => setError(String(e.message ?? e)));
  }, []);

  const key = (g) => `${g.domain}|${g.category}|${g.name}`;
  const chosen = (data?.groups ?? []).filter((g) => !skip.has(key(g)));
  const dropping = chosen.reduce((n, g) => n + g.drop.length, 0);

  async function remove() {
    setBusy(true);
    try {
      // One target per row being dropped, each pinned by book and page so the
      // survivor is never the one removed.
      await onRemove(chosen.flatMap((g) => g.drop.map((d) => ({
        book: g.book, domain: g.domain, category: g.category,
        id: d.id, srcBook: d.book, srcPage: d.page,
      }))));
      onClose();
    } catch (e) {
      setError(String(e.message ?? e));
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal dupes" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Duplicate names</h3>
          <button className="ghost tiny" onClick={onClose}>Close</button>
        </div>

        {error && <div className="modal-error">{error}</div>}
        {!data && !error && <p className="muted">Scanning the library…</p>}

        {data && (
          <>
            <p className="setup-hint">
              {data.names} duplicated name(s), {data.redundant} redundant row(s).
              The kept row is the Commlink6 one, then the fullest, then the
              earliest book. Untick a row to leave it alone.
            </p>
            <div className="dupe-list">
              {data.groups.map((g) => (
                <div className={`dupe ${skip.has(key(g)) ? "skipped" : ""}`} key={key(g)}>
                  <label className="dupe-head">
                    <input
                      type="checkbox"
                      checked={!skip.has(key(g))}
                      onChange={() => setSkip((s) => {
                        const n = new Set(s);
                        if (n.has(key(g))) n.delete(key(g)); else n.add(key(g));
                        return n;
                      })}
                    />
                    <span className="dupe-name">{g.name}</span>
                    <span className="badge">{g.domain}/{g.category}</span>
                  </label>
                  <div className="dupe-row keep">
                    KEEP <code>{g.keep.id}</code>
                    <span className="badge">{g.keep.book} p.{g.keep.page}</span>
                    <span className="badge">{g.keep.source}</span>
                    <span className="badge">{g.keep.fields} fields</span>
                  </div>
                  {g.drop.map((d, i) => (
                    <div className="dupe-row drop" key={i}>
                      DROP <code>{d.id}</code>
                      <span className="badge">{d.book} p.{d.page}</span>
                      <span className="badge">{d.source}</span>
                      <span className="badge">{d.fields} fields</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button className="primary" disabled={busy || !dropping} onClick={remove}>
                {busy ? "Removing…" : `Remove ${dropping} row(s)`}
              </button>
              <button className="ghost" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
