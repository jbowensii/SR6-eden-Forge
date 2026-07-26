import React, { useEffect, useState } from "react";
import CategoryTable from "./components/CategoryTable.jsx";
import ItemEditor from "./components/ItemEditor.jsx";
import Preview from "./components/Preview.jsx";
import Tree from "./components/Tree.jsx";
import { exportModule, getCategory, getTree, putItem, validate } from "./api.js";

export default function App() {
  const [tree, setTree] = useState([]);
  const [selected, setSelected] = useState(null); // {book, domain, category}
  const [payload, setPayload] = useState(null);
  const [editing, setEditing] = useState(null); // item
  const [doc, setDoc] = useState(null);
  const [issues, setIssues] = useState(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    getTree().then(setTree).catch((e) => setStatus(String(e)));
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

  async function runExport() {
    setStatus("exporting…");
    try {
      const res = await exportModule(selected.book, selected.domain, "all");
      setStatus(`exported ${res.count} item(s) -> ${res.moduleDir}`);
    } catch (e) {
      setStatus(`error: ${e.message ?? e}`);
    }
  }

  return (
    <div className="layout">
      <aside>
        <h1>SR6 Forge</h1>
        <button onClick={runValidate}>Validate all</button>
        <button onClick={runExport} disabled={!selected}>Export…</button>
        <Tree entries={tree} selected={selected} onSelect={openCategory} />
      </aside>
      <main>
        <div className="status">{status}</div>
        {payload && (
          <CategoryTable
            payload={payload}
            issues={issues}
            onEdit={(item) => {
              setEditing(item);
              setDoc(null);
            }}
          />
        )}
      </main>
      <section className="right">
        {editing && <ItemEditor key={editing.id} item={editing} onSave={save} />}
        {doc && <Preview doc={doc} />}
      </section>
    </div>
  );
}
