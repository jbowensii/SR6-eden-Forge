import React, { useEffect, useState } from "react";
import CategoryTable from "./components/CategoryTable.jsx";
import ItemEditor from "./components/ItemEditor.jsx";
import Preview from "./components/Preview.jsx";
import Tree from "./components/Tree.jsx";
import { assignIcon, exportModule, getBooks, getCategory, getTree, putItem, validate } from "./api.js";

export default function App() {
  const [tree, setTree] = useState([]);
  const [books, setBooks] = useState({});
  const [selected, setSelected] = useState(null); // {book, domain, category}
  const [exporting, setExporting] = useState(false);
  const [payload, setPayload] = useState(null);
  const [editing, setEditing] = useState(null); // item
  const [doc, setDoc] = useState(null);
  const [issues, setIssues] = useState(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    getTree().then(setTree).catch((e) => setStatus(String(e)));
    getBooks().then(setBooks).catch(() => {});
  }, []);

  async function openCategory(entry) {
    try {
      setSelected(entry);
      setEditing(null);
      setDoc(null);
      setPayload(await getCategory(entry.book, entry.domain, entry.category));
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    }
  }

  async function save(item) {
    try {
      const res = await putItem(selected.book, selected.domain, selected.category, item);
      setDoc(res.doc);
      setStatus(res.docError ? `saved; preview error: ${res.docError}` : `saved ${item.id}`);
      setPayload(await getCategory(selected.book, selected.domain, selected.category));
      setTree(await getTree());
      setEditing(res.item);
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
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

  async function handleAssignIcon(item, hit, mode) {
    const res = await assignIcon({
      book: selected.book,
      domain: selected.domain,
      category: selected.category,
      itemId: item.id,
      root: hit.r,
      libraryPath: hit.p,
      mode,
    });
    setStatus(mode === "generic" ? `generic icon updated (${res.updated} item(s))` : `icon set for ${item.id}`);
    setPayload(await getCategory(selected.book, selected.domain, selected.category));
    const fresh = (await getCategory(selected.book, selected.domain, selected.category)).items.find((i) => i.id === item.id);
    if (fresh) setEditing(fresh);
  }

  async function runExport() {
    if (exporting) return;
    // "all" while QA is in progress; switch to "approved" for release exports
    const exportStatus = "all";
    setExporting(true);
    setStatus(`exporting (status: ${exportStatus})…`);
    try {
      const res = await exportModule(selected.book, selected.domain, exportStatus);
      setStatus(`exported ${res.count} item(s) (status: ${exportStatus}) -> ${res.moduleDir}`);
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    } finally {
      setExporting(false);
    }
  }

  const bookInfo = selected ? books[selected.book] : null;

  return (
    <div className="layout">
      <aside>
        <header className="brand">
          <span className="brand-sr6">SR6</span>
          <span className="brand-slash">//</span>
          <span className="brand-forge">FORGE</span>
        </header>
        <div className="actions">
          <button onClick={runValidate}>Validate</button>
          <button onClick={runExport} disabled={!selected || exporting}>Export</button>
        </div>
        <Tree entries={tree} selected={selected} onSelect={openCategory} />
      </aside>
      <main>
        <div className="status" data-live={Boolean(status)}>{status || "ready"}</div>
        {payload ? (
          <CategoryTable
            payload={payload}
            issues={issues}
            onEdit={(item) => {
              setEditing(item);
              setDoc(null);
            }}
          />
        ) : (
          <div className="empty-slate">
            <div className="empty-glyph">⬡</div>
            <p>Select a category to start the run.</p>
          </div>
        )}
      </main>
      <section className="right">
        {editing && (
          <ItemEditor
            key={editing.id}
            item={editing}
            bookTitle={bookInfo?.title ?? selected?.book}
            pdfAvailable={Boolean(bookInfo?.pdf)}
            pdfHref={editing.meta ? `/api/pdf/${editing.meta.book}#page=${editing.meta.page}` : null}
            onSave={save}
            onAssignIcon={handleAssignIcon}
          />
        )}
        {doc && <Preview doc={doc} />}
      </section>
    </div>
  );
}
