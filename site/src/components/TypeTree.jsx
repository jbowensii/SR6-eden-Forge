import React, { useState } from "react";
import { prettySubtype, prettyType } from "../labels.js";

// TYPE -> SUBTYPE nested tree. A type row expands to its subtypes; clicking a
// type or a subtype loads the items under it. The "" subtype is shown as an
// explicit "(no subtype)" bucket so gaps are visible, not hidden.
export default function TypeTree({ tree, selected, onSelect }) {
  const [open, setOpen] = useState(() => new Set());

  const toggle = (type) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });

  const isActive = (type, subtype) =>
    selected && selected.type === type && (selected.subtype ?? null) === (subtype ?? null);

  return (
    <nav className="type-tree">
      {tree.map((t) => {
        const expanded = open.has(t.type);
        const done = t.qa.reviewed + t.qa.approved;
        // a single subtype (e.g. Foci -> Focus) adds no information: treat the
        // type as a leaf and load all its items when clicked, no sublevel.
        const hasChildren = t.subtypes.length > 1;
        return (
          <div key={t.type} className="type-group">
            <div className={`tree-row type-row ${isActive(t.type, undefined) ? "active" : ""}`}>
              <button
                className="twisty"
                title={expanded ? "Collapse" : "Expand"}
                disabled={!hasChildren}
                onClick={(e) => { e.stopPropagation(); if (hasChildren) toggle(t.type); }}
              >
                {hasChildren ? (expanded ? "▾" : "▸") : "·"}
              </button>
              <span className="tree-name type-name" onClick={() => onSelect({ type: t.type })}>
                {prettyType(t.type)}
              </span>
              <span className="badge" title={`${t.qa.extracted} extracted · ${t.qa.reviewed} reviewed · ${t.qa.approved} approved`}>
                {t.items}
              </span>
              <span className="qa-bar" style={{ "--pct": `${t.items ? Math.round((done / t.items) * 100) : 0}%` }} />
            </div>
            {expanded && hasChildren &&
              t.subtypes.map((s) => (
                <div
                  key={s.subtype || "_none"}
                  className={`tree-row subtype-row ${isActive(t.type, s.subtype) ? "active" : ""}`}
                  onClick={() => onSelect({ type: t.type, subtype: s.subtype })}
                >
                  <span className={`tree-name ${s.subtype ? "" : "no-subtype"}`}>
                    {s.subtype ? prettySubtype(s.subtype) : "(no subtype)"}
                  </span>
                  <span className="badge">{s.items}</span>
                </div>
              ))}
          </div>
        );
      })}
    </nav>
  );
}
