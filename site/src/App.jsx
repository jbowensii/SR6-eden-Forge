import React, { useCallback, useEffect, useRef, useState } from "react";
import CategoryTable from "./components/CategoryTable.jsx";
import ItemEditor from "./components/ItemEditor.jsx";
import Preview from "./components/Preview.jsx";
import TypeTree from "./components/TypeTree.jsx";
import SetupPanel from "./components/SetupPanel.jsx";
import Duplicates from "./components/Duplicates.jsx";
import { applyCorrections, assignIcon, assignRender, deleteItem, deleteItems, exportModule, getBooks, getCategory, getDomains, getItems, getTypeTree, patchItems, putItem, searchItems, validate } from "./api.js";

export default function App() {
  const [tree, setTree] = useState([]);      // primary -> secondary tree for the domain
  const [domain, setDomain] = useState("gear");
  const [domainList, setDomainList] = useState(["gear"]);
  const [books, setBooks] = useState({});
  const [selected, setSelected] = useState(null); // {type, subtype?} or {book,domain,category}
  const [exporting, setExporting] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const [payload, setPayload] = useState(null);
  const [editing, setEditing] = useState(null); // item
  // Which column the middle pane is sorted by. Lives here so it outlives the
  // table: choose a column once and every category you open afterwards keeps
  // it, until another is chosen or the page is reloaded.
  const [sort, setSort] = useState({ key: "name", dir: 1 });
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [menu, setMenu] = useState(null);       // {x, y, ids} right-click menu
  const [dupesOpen, setDupesOpen] = useState(false);
  // Whether the editor is holding unsaved changes. A ref, not state: the guard
  // is read inside event handlers, and a stale closure here would wave through
  // exactly the edit it exists to protect.
  const dirtyRef = useRef(false);
  // Stable, so the editor's dirty-reporting effect fires when the flag
  // changes rather than on every render.
  const noteDirty = useCallback((d) => { dirtyRef.current = d; }, []);
  const [doc, setDoc] = useState(null);
  const [issues, setIssues] = useState(null);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null); // null = not searching; [] = no hits

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(null);
      return;
    }
    const t = setTimeout(() => {
      searchItems(q).then(setResults).catch(() => setResults([]));
    }, 180);
    return () => clearTimeout(t);
  }, [query]);

  async function openItem(hit) {
    try {
      setSelected({ book: hit.book, domain: hit.domain, category: hit.category });
      setDoc(null);
      const p = await getCategory(hit.book, hit.domain, hit.category);
      setPayload(p);
      const found = p.items.find((i) => i.id === hit.id);
      setEditing(found ? { ...found, _book: hit.book, _domain: hit.domain, _category: hit.category } : null);
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    }
  }

  useEffect(() => {
    getDomains().then((r) => setDomainList(r.domains?.length ? r.domains : ["gear"])).catch(() => {});
    getBooks().then(setBooks).catch(() => {});
  }, []);

  useEffect(() => {
    getTypeTree(domain).then(setTree).catch((e) => setStatus(String(e)));
    setSelected(null);
    setPayload(null);
    setEditing(null);
  }, [domain]);

  async function openType(sel) {
    try {
      setSelected(sel);
      setEditing(null);
      setDoc(null);
      const res = await getItems(sel.type, sel.subtype, domain);
      // items carry their source category/book so edits still route correctly
      setPayload({ book: sel.type, domain, category: sel.subtype ?? sel.type, items: res.items });
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    }
  }

  async function refreshPayload() {
    if (!selected) return;
    if (selected.type) setPayload({ ...(await getItems(selected.type, selected.subtype, domain)), book: selected.type, domain, category: selected.subtype ?? selected.type });
    else setPayload(await getCategory(selected.book, selected.domain, selected.category));
  }

  async function save(item) {
    // route by the item's own source file (type/subtype views mix categories)
    const book = item._book ?? selected.book;
    const domain = item._domain ?? selected.domain;
    const category = item._category ?? selected.category;
    const clean = { ...item };
    delete clean._book; delete clean._domain; delete clean._category;
    try {
      const res = await putItem(book, domain, category, clean);
      setDoc(res.doc);
      setStatus(res.docError ? `saved; preview error: ${res.docError}` : `saved ${item.id}`);
      // update the center table immediately (name/subtype/etc.), then reconcile
      setPayload((p) => (p ? { ...p, items: p.items.map((i) => (i.id === res.item.id ? { ...i, ...res.item } : i)) } : p));
      await refreshPayload();
      setTree(await getTypeTree(domain));
      setEditing({ ...res.item, _book: book, _domain: domain, _category: category });
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    }
  }

  async function remove(item) {
    const book = item._book ?? selected?.book;
    const domain = item._domain ?? selected?.domain;
    const category = item._category ?? selected?.category;
    try {
      await deleteItem(book, domain, category, item.id);
      setEditing(null);
      setDoc(null);
      await refreshPayload();
      setTree(await getTypeTree(domain));
      setStatus(`deleted ${item.id}`);
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    }
  }

  const [applyingCorr, setApplyingCorr] = useState(false);
  async function runApplyCorrections() {
    if (applyingCorr) return;
    setApplyingCorr(true);
    setStatus("applying manual corrections…");
    try {
      const res = await applyCorrections();
      setStatus(res.ok
        ? `corrections applied: ${res.applied ?? "?"} overlaid, ${res.deletions ?? 0} deletion(s)`
        : `corrections failed (exit ${res.code}) — ${res.log?.slice(-1)[0] ?? ""}`);
      if (res.ok) {
        await refreshPayload();               // reflect restored edits in the center
        setTree(await getTypeTree(domain));
      }
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    } finally {
      setApplyingCorr(false);
    }
  }

  async function runValidate() {
    setStatus("validating…");
    try {
      const res = await validate();
      setIssues(res.issues);
      setStatus(res.ok ? `validator: OK (${res.items} items)` : `validator: ${res.issues.length} issue(s)`);
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    }
  }

  // Re-read an item from disk and put it back in the right pane.
  //
  // Anything that changes an item on the server has to end here. Patching the
  // local draft instead looks like it worked and is not the same thing: the art
  // search did that, so a downloaded picture updated `img` in the pane while
  // meta.render, the displaced icon and the rewritten description -- all set by
  // the server -- never arrived, and the render slot stayed empty until a reload.
  async function reloadEditing(item) {
    const book = item._book ?? selected?.book;
    const domain = item._domain ?? selected?.domain;
    const category = item._category ?? selected?.category;
    if (!book || !domain || !category) return;
    await refreshPayload();
    setTree(await getTypeTree(domain));       // art/counts show in the left pane too
    const fresh = (await getCategory(book, domain, category)).items.find((i) => i.id === item.id);
    if (fresh) setEditing({ ...fresh, _book: book, _domain: domain, _category: category });
  }

  async function handleAssignIcon(item, hit, mode) {
    const book = item._book ?? selected.book;
    const domain = item._domain ?? selected.domain;
    const category = item._category ?? selected.category;
    const res = await assignIcon({ book, domain, category, itemId: item.id, root: hit.r, libraryPath: hit.p, mode });
    setStatus(mode === "generic" ? `generic icon updated (${res.updated} item(s))` : `icon set for ${item.id}`);
    await reloadEditing(item);
  }

  // the art search assigns on the server too, so it refreshes the same way
  async function handleArtAssigned(item) {
    await reloadEditing(item);
    setStatus(`artwork set for ${item.id}`);
  }

  async function handleAssignRender(item, imagePath) {
    const book = item._book ?? selected?.book;
    const domain = item._domain ?? selected?.domain;
    const category = item._category ?? selected?.category;
    try {
      await assignRender({ book, domain, category, itemId: item.id, imagePath });
      await reloadEditing(item);
      setStatus(`render set for ${item.id}`);
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    }
  }

  async function runExport() {
    if (exporting) return;
    // "all" while QA is in progress; switch to "approved" for release exports
    const exportStatus = "all";
    setExporting(true);
    setStatus(`exporting (status: ${exportStatus})…`);
    try {
      // the whole merged library lives under the corebook/gear namespace
      const res = await exportModule("corebook", "gear", exportStatus);
      setStatus(`exported ${res.count} item(s) (status: ${exportStatus}) -> ${res.moduleDir}`);
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    } finally {
      setExporting(false);
    }
  }

  // ── the one door in and out of the editor ────────────────────────────────
  //
  // Every user-driven change of what is being edited goes through here. The
  // bug this exists to stop: ItemEditor is keyed by item id, so selecting a
  // different row remounted it and rebuilt the draft from the new item —
  // silently discarding anything typed and not saved. There was no dirty flag
  // anywhere in the app, so nothing could have noticed.
  //
  // Returns false when the user declines, and callers must respect that.
  // Programmatic updates after a save or delete set `editing` directly: they
  // are not navigation, and there is nothing unsaved left to protect.
  function requestSelection(next) {
    if (dirtyRef.current && next?.id !== editing?.id) {
      if (!window.confirm("You have unsaved changes. Discard them?")) return false;
    }
    dirtyRef.current = false;
    setEditing(next ?? null);
    setDoc(null);
    return true;
  }

  // Closing the tab is the other way to lose an edit, and the only one the app
  // cannot draw its own dialog for.
  useEffect(() => {
    const warn = (e) => {
      if (!dirtyRef.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  // A right-click menu that survives the next click would be its own bug.
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", close);
    };
  }, [menu]);

  // Apply ONE delta to every selected item. `changes` holds only the fields
  // the user actually touched, so values that merely differ across the
  // selection are left alone rather than flattened to whatever the editor
  // happened to be showing.
  async function bulkSave(changes) {
    const chosen = (payload?.items ?? []).filter((i) => selectedIds.has(i.id));
    if (!chosen.length || !Object.keys(changes).length) return;
    const targets = chosen.map((i) => ({
      book: i._book ?? i.meta.book, domain: i._domain ?? payload.domain,
      category: i._category ?? payload.category, id: i.id,
    }));
    setStatus(`saving ${targets.length}…`);
    try {
      const res = await patchItems(targets, changes);
      dirtyRef.current = false;
      await refreshPayload();
      setTree(await getTypeTree(domain));
      setStatus(res.failed?.length
        ? `saved ${res.updated}, ${res.failed.length} failed`
        : `saved ${res.updated} item(s)`);
    } catch (err) {
      setStatus(`bulk save failed — ${err.message}`);
    }
  }

  async function deleteSelected(ids) {
    const chosen = (payload?.items ?? []).filter((i) => ids.has(i.id));
    if (!chosen.length) return;
    const names = chosen.slice(0, 12).map((i) => `  • ${i.name}`).join("\n");
    const more = chosen.length > 12 ? `\n  …and ${chosen.length - 12} more` : "";
    // Named, not just counted. Deleting is the one correction that cannot be
    // checked afterwards by looking at the library, because the evidence of a
    // mistake is an absence.
    if (!window.confirm(`Delete ${chosen.length} item(s)?\n\n${names}${more}`)) return;

    const targets = chosen.map((i) => ({
      book: i._book ?? i.meta.book, domain: i._domain ?? payload.domain,
      category: i._category ?? payload.category, id: i.id,
    }));
    setStatus(`deleting ${targets.length}…`);
    try {
      const res = await deleteItems(targets);
      dirtyRef.current = false;
      setEditing(null);
      setSelectedIds(new Set());
      await refreshPayload();
      setStatus(res.failed?.length
        ? `deleted ${res.deleted}, ${res.failed.length} failed`
        : `deleted ${res.deleted}`);
    } catch (err) {
      setStatus(`delete failed — ${err.message}`);
    }
  }

  // the library is a merged namespace: each item's real source is meta.book,
  // not the selected library folder. Show the title/PDF for the item's own book.
  const bookInfo = editing?.meta?.book ? books[editing.meta.book] : null;

  // draggable pane widths (persisted). The layout grid reads --left-w / --right-w.
  const layoutRef = useRef(null);
  useEffect(() => {
    const root = layoutRef.current; if (!root) return;
    const l = localStorage.getItem("sr6-left"); const r = localStorage.getItem("sr6-right");
    if (l) root.style.setProperty("--left-w", l);
    if (r) root.style.setProperty("--right-w", r);
  }, []);
  const startDrag = (which) => (e) => {
    e.preventDefault();
    const root = layoutRef.current;
    const startX = e.clientX;
    const cs = getComputedStyle(root);
    const startL = parseInt(cs.getPropertyValue("--left-w")) || 300;
    const startR = parseInt(cs.getPropertyValue("--right-w")) || 400;
    const onMove = (ev) => {
      const dx = ev.clientX - startX;
      if (which === "left") root.style.setProperty("--left-w", `${Math.min(560, Math.max(190, startL + dx))}px`);
      else root.style.setProperty("--right-w", `${Math.min(900, Math.max(300, startR - dx))}px`);
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      localStorage.setItem("sr6-left", root.style.getPropertyValue("--left-w"));
      localStorage.setItem("sr6-right", root.style.getPropertyValue("--right-w"));
    };
    document.body.style.cursor = "col-resize";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  return (
    <div className="layout" ref={layoutRef}>
      <aside>
        <header className="brand">
          <svg className="brand-mark" viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
            <path d="M16 3.2 27 9.4 27 22.6 16 28.8 5 22.6 5 9.4Z" fill="none"
              stroke="var(--magenta)" strokeWidth="2" strokeLinejoin="miter" />
            <text x="16" y="22.4" textAnchor="middle" fontFamily="var(--font-display)"
              fontSize="18" fontWeight="700" fill="var(--magenta-soft)">6</text>
          </svg>
          <span className="brand-sr6">SR6</span>
          <span className="brand-slash">//</span>
          <span className="brand-forge">FORGE</span>
        </header>
        <div className="actions">
          <button onClick={runValidate}>Validate</button>
          <button onClick={() => setDupesOpen(true)} title="Find items sharing a name">Duplicates</button>
          <button onClick={runApplyCorrections} disabled={applyingCorr} title="Re-overlay every manual correction (data/_corrections) onto the data files">
            {applyingCorr ? "Applying…" : "Apply corrections"}
          </button>
          <button onClick={runExport} disabled={!selected || exporting}>Export</button>
          <button onClick={() => setSetupOpen(true)} title="Configure book paths and rebuild the library">⚙ Setup</button>
        </div>
        {domainList.length > 1 && (
          <div className="domain-tabs">
            {domainList.map((d) => (
              <button
                key={d}
                className={`domain-tab ${d === domain ? "active" : ""}`}
                onClick={() => setDomain(d)}
              >
                {d}
              </button>
            ))}
          </div>
        )}
        <div className="search">
          <input
            type="search"
            className="search-input"
            placeholder="Find an item…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button className="search-clear" title="Clear" onClick={() => setQuery("")}>×</button>
          )}
        </div>
        {results === null ? (
          <TypeTree tree={tree} selected={selected} onSelect={openType} />
        ) : (
          <nav className="search-results">
            <div className="tree-group-title">{results.length} match{results.length === 1 ? "" : "es"}</div>
            {results.map((hit) => (
              <div
                key={`${hit.category}/${hit.id}`}
                className={`tree-row ${editing?.id === hit.id ? "active" : ""}`}
                onClick={() => openItem(hit)}
                title={`${hit.category.replace(/_/g, " ")} · ${books[hit.sourceBook]?.title ?? hit.sourceBook}`}
              >
                <span className="tree-name">{hit.name}</span>
                <span className="badge">{hit.category.replace(/_/g, " ")}</span>
              </div>
            ))}
          </nav>
        )}
      </aside>
      <div className="splitter" title="Drag to resize" onMouseDown={startDrag("left")} />
      <main>
        <div className="status" data-live={Boolean(status)}>{status || "ready"}</div>
        {payload ? (
          <>
            <label className="attention-filter">
              <input
                type="checkbox"
                checked={attentionOnly}
                onChange={(e) => setAttentionOnly(e.target.checked)}
              />
              Show only incomplete / warnings
            </label>
            <CategoryTable
              sort={sort}
              onSortChange={setSort}
              payload={payload}
              issues={issues}
              needsAttention={attentionOnly}
              selectedIds={selectedIds}
              onSelectionChange={(ids, focus) => {
                if (!requestSelection(focus)) return;   // dirty and declined
                setSelectedIds(ids);
              }}
              onContextMenu={setMenu}
              onEdit={() => setDoc(null)}
            />
          </>
        ) : (
          <div className="empty-slate">
            <div className="empty-glyph">⬡</div>
            <p>Select a category to start the run.</p>
          </div>
        )}
      </main>
      <div className="splitter" title="Drag to resize" onMouseDown={startDrag("right")} />
      <section className="right">
        {editing && (
          <ItemEditor
            key={editing.id}
            item={editing}
            selectedItems={(payload?.items ?? []).filter((i) => selectedIds.has(i.id))}
            onDirtyChange={noteDirty}
            onBulkSave={bulkSave}
            domain={editing._domain ?? domain}
            bookTitle={bookInfo?.title ?? editing?.meta?.book ?? selected?.book}
            books={books}
            categoryName={(editing?._category ?? selected?.category ?? selected?.subtype ?? selected?.type)?.replace(/_/g, " ")}
            pdfAvailable={Boolean(bookInfo?.pdf)}
            // meta.page is the number PRINTED on the page; a PDF viewer counts
            // files pages. books.json carries the measured difference per book
            // (tools/detect_page_offsets.py), 0 when it could not be read.
            pdfHref={editing.meta ? `/api/pdf/${editing.meta.book}?i=${encodeURIComponent(editing.id)}#page=${Number(editing.meta.page || 0) + Number(books[editing.meta.book]?.pageOffset || 0)}` : null}
            onSave={save}
            onDelete={remove}
            onAssignIcon={handleAssignIcon}
            onAssignRender={handleAssignRender}
            onArtAssigned={handleArtAssigned}
          />
        )}
        {doc && <Preview doc={doc} />}
      </section>
      {menu && (
        // Positioned where the cursor was. Dismissed by the window listener
        // above, so any click anywhere closes it.
        <ul className="ctx-menu" style={{ left: menu.x, top: menu.y }}
            onClick={(e) => e.stopPropagation()}>
          <li onClick={() => { setMenu(null); deleteSelected(menu.ids); }}>
            Delete {menu.ids.size} selected
          </li>
        </ul>
      )}
      {dupesOpen && (
        <Duplicates
          onClose={() => setDupesOpen(false)}
          onRemove={async (targets) => {
            setStatus(`removing ${targets.length} duplicate row(s)…`);
            const res = await deleteItems(targets);
            dirtyRef.current = false;
            setEditing(null);
            setSelectedIds(new Set());
            await refreshPayload();
            setTree(await getTypeTree(domain));
            setStatus(res.failed?.length
              ? `removed ${res.deleted}, ${res.failed.length} failed`
              : `removed ${res.deleted} duplicate row(s)`);
          }}
        />
      )}
      {setupOpen && <SetupPanel onClose={() => setSetupOpen(false)} />}
    </div>
  );
}
