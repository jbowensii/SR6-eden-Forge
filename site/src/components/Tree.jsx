import React from "react";

export default function Tree({ entries, selected, onSelect }) {
  return (
    <nav>
      {entries.map((e) => {
        const key = `${e.book}/${e.domain}/${e.category}`;
        const active = selected && key === `${selected.book}/${selected.domain}/${selected.category}`;
        return (
          <div key={key} className={`tree-row ${active ? "active" : ""}`} onClick={() => onSelect(e)}>
            <span>{key}</span>
            <span className="badge">
              {e.items} · {e.qa.approved}✓
            </span>
          </div>
        );
      })}
    </nav>
  );
}
