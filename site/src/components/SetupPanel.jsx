import React, { useEffect, useRef, useState } from "react";
import { getBooksConfig, putBooksConfig, startRebuild, rebuildStatus, getSearchConfig, putSearchConfig } from "../api.js";

// Setup panel: point each registered book at its source PDF, then trigger the
// extraction pipeline that (re)builds the site's data. Rebuild runs server-side;
// this polls its log.
export default function SetupPanel({ onClose }) {
  const [books, setBooks] = useState([]);
  const [paths, setPaths] = useState(null);
  const [search, setSearch] = useState({ engine: "scrape", hasKey: false, cseId: "", prefix: "shadowrun cyberpunk" });
  const [apiKey, setApiKey] = useState("");
  const [edits, setEdits] = useState({});          // slug -> new pdf path
  const [saveMsg, setSaveMsg] = useState("");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState([]);
  const logRef = useRef(null);
  const poll = useRef(null);

  const load = () => getBooksConfig().then((r) => { setBooks(r.books); setPaths(r.paths); }).catch(() => {});
  useEffect(() => { load(); getSearchConfig().then(setSearch).catch(() => {}); return () => clearInterval(poll.current); }, []);

  const saveSearch = async () => {
    await putSearchConfig({ engine: search.engine, cseId: search.cseId, prefix: search.prefix,
      ...(apiKey ? { apiKey } : {}) });
    setApiKey("");
    getSearchConfig().then(setSearch).catch(() => {});
    setSaveMsg("search settings saved");
    setTimeout(() => setSaveMsg(""), 3000);
  };
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [log]);

  const setPath = (slug, pdf) => setEdits((e) => ({ ...e, [slug]: pdf }));

  const save = async () => {
    if (!Object.keys(edits).length) return;
    const r = await putBooksConfig(edits);
    setSaveMsg(`saved ${r.changed} path(s)`);
    setEdits({});
    load();
    setTimeout(() => setSaveMsg(""), 3000);
  };

  const startPolling = () => {
    clearInterval(poll.current);
    poll.current = setInterval(async () => {
      const s = await rebuildStatus().catch(() => null);
      if (!s) return;
      setLog(s.log);
      setRunning(s.running);
      if (!s.running) { clearInterval(poll.current); load(); }
    }, 1500);
  };

  const rebuild = async () => {
    if (Object.keys(edits).length) await save();
    setRunning(true); setLog(["starting rebuild…"]);
    await startRebuild().catch((e) => setLog([`failed to start: ${e.message}`]));
    startPolling();
  };

  const missing = books.filter((b) => !b.exists && (edits[b.slug] ?? b.pdf)).length;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal setup-panel" onClick={(e) => e.stopPropagation()}>
        <div className="setup-head">
          <h2>Library Setup</h2>
          <button className="ghost" onClick={onClose}>✕</button>
        </div>
        <p className="setup-hint">
          Point each book at its source PDF, then rebuild the library. Paths are
          absolute (e.g. <code>C:/Users/you/Books/Core.pdf</code>). Missing files
          are highlighted; books without a PDF are skipped during import.
        </p>

        {paths && (
          <div className="path-info">
            <div><span className="path-label">Data</span><code>{paths.data}</code></div>
            <div><span className="path-label">Extracted art</span><code>{paths.art}</code></div>
            <div><span className="path-label">Icon library</span><code>{paths.iconLibrary}</code></div>
          </div>
        )}

        <div className="search-config">
          <div className="sc-title">Artwork search</div>
          <div className="sc-row">
            <label>Engine
              <select value={search.engine} onChange={(e) => setSearch({ ...search, engine: e.target.value })}>
                <option value="scrape">Bing (scrape, no key)</option>
                <option value="bing">Bing Image Search API (key)</option>
                <option value="google">Google Custom Search (key + CSE)</option>
              </select>
            </label>
            <label>Query prefix
              <input type="text" value={search.prefix} onChange={(e) => setSearch({ ...search, prefix: e.target.value })} />
            </label>
          </div>
          {search.engine !== "scrape" && (
            <div className="sc-row">
              <label>API key
                <input type="password" value={apiKey} placeholder={search.hasKey ? "•••••• (set — leave blank to keep)" : "paste key"}
                  onChange={(e) => setApiKey(e.target.value)} />
              </label>
              {search.engine === "google" && (
                <label>CSE id
                  <input type="text" value={search.cseId} onChange={(e) => setSearch({ ...search, cseId: e.target.value })} />
                </label>
              )}
            </div>
          )}
          <button className="ghost" onClick={saveSearch}>Save search settings</button>
        </div>

        <div className="book-config">
          {books.map((b) => {
            const val = edits[b.slug] ?? b.pdf;
            const ok = b.slug in edits ? null : b.exists;
            return (
              <label key={b.slug} className={`book-row ${ok === false ? "missing" : ""}`}>
                <span className="book-title" title={b.slug}>{b.title}</span>
                <input type="text" value={val} placeholder="path to .pdf"
                  onChange={(e) => setPath(b.slug, e.target.value)} />
                <span className="book-status">{ok === false ? "missing" : ok ? "✓" : "?"}</span>
              </label>
            );
          })}
        </div>

        <div className="setup-actions">
          <button className="ghost" onClick={save} disabled={!Object.keys(edits).length}>Save paths</button>
          <button className="primary" onClick={rebuild} disabled={running}>
            {running ? "Rebuilding…" : "Rebuild library"}
          </button>
          {saveMsg && <span className="save-msg">{saveMsg}</span>}
          {missing > 0 && <span className="warn-msg">{missing} path(s) still missing</span>}
        </div>

        {(log.length > 0 || running) && (
          <pre className="rebuild-log" ref={logRef}>
            {log.join("\n")}
          </pre>
        )}
      </div>
    </div>
  );
}
