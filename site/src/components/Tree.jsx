import React from "react";

export default function Tree({ entries, selected, onSelect }) {
  const groups = new Map();
  for (const e of entries) {
    const g = `${e.book} // ${e.domain}`;
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(e);
  }
  return (
    <nav>
      {[...groups.entries()].map(([group, list]) => (
        <div key={group} className="tree-group">
          <div className="tree-group-title">{group}</div>
          {list.map((e) => {
            const key = `${e.book}/${e.domain}/${e.category}`;
            const active = selected && key === `${selected.book}/${selected.domain}/${selected.category}`;
            const pct = e.items ? Math.round(((e.qa.reviewed + e.qa.approved) / e.items) * 100) : 0;
            return (
              <div key={key} className={`tree-row ${active ? "active" : ""}`} onClick={() => onSelect(e)}>
                <span className="tree-name">{e.category.replace(/_/g, " ")}</span>
                <span className="badge" title={`${e.qa.extracted} extracted · ${e.qa.reviewed} reviewed · ${e.qa.approved} approved`}>
                  {e.items}
                </span>
                <span className="qa-bar" style={{ "--pct": `${pct}%` }} />
              </div>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
