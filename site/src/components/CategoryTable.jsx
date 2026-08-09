import React, { useMemo, useRef, useState } from "react";
import { needsAttention as itemNeedsAttention } from "../../shared/edenSpec.mjs";

const EMPTY = new Set();

// number embedded in a stat string like "1,200¥" / "8R" -> comparable number
const num = (v) => {
  const m = String(v ?? "").replace(/,/g, "").match(/-?\d+(?:\.\d+)?/);
  return m ? Number(m[0]) : Number.NEGATIVE_INFINITY;
};
const QA_ORDER = { extracted: 0, reviewed: 1, approved: 2 };

// column key -> accessor + type (for sort). Header order matches COLUMNS.
const COLUMNS = [
  { key: "name", label: "Name", get: (it) => it.name, type: "str" },
  { key: "subtype", label: "Subtype", get: (it) => it.system.subtype ?? "", type: "str" },
  { key: "price", label: "Price", get: (it) => it.system.priceDef || it.system.price || "", type: "num" },
  { key: "avail", label: "Avail", get: (it) => it.system.availDef || it.system.avail || "", type: "num" },
  // rated gear prices per rating; show the range and the spread so a reviewer
  // can see the whole ladder rather than just the rating-1 figure
  { key: "rating", label: "Rating",
    get: (it) => {
      const f = it.system.sr6forge;
      return f?.ratings?.length ? `${f.ratings[0]}-${f.maxRating}` : "";
    } },
  { key: "priceLadder", label: "Price by rating",
    get: (it) => (it.system.sr6forge?.priceByRating ?? []).join(" / ") },
  { key: "essence", label: "Essence",
    get: (it) => {
      const f = it.system.sr6forge;
      if (f?.essenceByRating?.length) return f.essenceByRating.join(" / ");
      return it.system.essence || "";
    } },
  { key: "page", label: "Ref", get: (it) => it.meta.page ?? 0, type: "num" },
  { key: "qa", label: "QA", get: (it) => QA_ORDER[it.meta.qaStatus] ?? 0, type: "num" },
];

export default function CategoryTable({
  payload, issues, onEdit,
  selectedIds = EMPTY, onSelectionChange, needsAttention, onContextMenu,
}) {
  const [sort, setSort] = useState({ key: null, dir: 1 });
  // Anchor for shift-ranges. Held here rather than in App because it only
  // means anything against THIS table's current sort order — re-sort and the
  // range a user sees is different from the range an index-based anchor gives.
  const anchor = useRef(null);

  const issueMap = useMemo(() => {
    const m = new Map();
    for (const issue of issues ?? []) {
      if (issue.item_id) m.set(issue.item_id, [...(m.get(issue.item_id) ?? []), issue]);
    }
    return m;
  }, [issues]);

  const rows = useMemo(() => {
    let items = [...payload.items];
    if (needsAttention) {
      items = items.filter((it) =>
        itemNeedsAttention(it, payload.domain, issueMap.get(it.id)?.length ?? 0));
    }
    if (!sort.key) return items;
    if (sort.key === "issues") {
      items.sort((a, b) => ((issueMap.get(a.id)?.length ?? 0) - (issueMap.get(b.id)?.length ?? 0)) * sort.dir);
      return items;
    }
    const col = COLUMNS.find((c) => c.key === sort.key);
    items.sort((a, b) => {
      const av = col.get(a), bv = col.get(b);
      const cmp = col.type === "num" ? num(av) - num(bv) : String(av).localeCompare(String(bv), undefined, { numeric: true });
      return cmp * sort.dir;
    });
    return items;
  }, [payload.items, payload.domain, sort, issueMap, needsAttention]);

  const toggle = (key) => setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: 1 }));
  const caret = (key) => (sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : "");

  // Plain click  — open this one, selection becomes just it.
  // Ctrl / Cmd    — add or remove one, keeping the rest.
  // Shift         — extend from the last plain-clicked row, in the order the
  //                 rows are CURRENTLY sorted, which is the order on screen.
  const clickRow = (item, index, e) => {
    if (e.shiftKey && anchor.current !== null) {
      const [lo, hi] = [anchor.current, index].sort((a, b) => a - b);
      const range = rows.slice(lo, hi + 1).map((r) => r.id);
      onSelectionChange?.(new Set(range), item);
      return;
    }
    if (e.ctrlKey || e.metaKey) {
      const next = new Set(selectedIds);
      if (next.has(item.id)) next.delete(item.id);
      else next.add(item.id);
      anchor.current = index;
      // Editing follows the row just clicked while it is still selected;
      // ctrl-clicking a row OFF should not leave the editor showing it.
      onSelectionChange?.(next, next.has(item.id) ? item : null);
      return;
    }
    anchor.current = index;
    onSelectionChange?.(new Set([item.id]), item);
    onEdit?.(item);
  };

  const rightClick = (item, index, e) => {
    e.preventDefault();
    // Right-clicking outside the selection acts on the row under the cursor,
    // which is what every file manager does. Inside it, the selection stands.
    let ids = selectedIds;
    if (!selectedIds.has(item.id)) {
      ids = new Set([item.id]);
      anchor.current = index;
      onSelectionChange?.(ids, item);
    }
    onContextMenu?.({ x: e.clientX, y: e.clientY, ids });
  };

  return (
    <table className="cat-table">
      <thead>
        <tr>
          {COLUMNS.map((c) => (
            <th key={c.key} className="sortable" onClick={() => toggle(c.key)} title="Click to sort">
              {c.label}{caret(c.key)}
            </th>
          ))}
          <th className="sortable" onClick={() => toggle("issues")} title="Click to sort">Issues{caret("issues")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((item, index) => (
          <tr
            key={item.id}
            className={selectedIds.has(item.id) ? "row-selected" : undefined}
            onClick={(e) => clickRow(item, index, e)}
            onContextMenu={(e) => rightClick(item, index, e)}
          >
            <td className="cell-name">
              {item.img && <span className="has-img" title={item.img}>◈</span>}
              {item.name}
            </td>
            <td className="cell-subtype">{item.system.subtype ?? ""}</td>
            <td className="cell-num">{item.system.priceDef || item.system.price}</td>
            <td className="cell-num">{item.system.availDef || item.system.avail}</td>
            <td className="cell-num">
              {item.system.sr6forge?.ratings?.length
                ? `${item.system.sr6forge.ratings[0]}-${item.system.sr6forge.maxRating}` : ""}
            </td>
            <td className="cell-num">
              {(item.system.sr6forge?.priceByRating ?? []).join(" / ")}
            </td>
            <td className="cell-num">
              {item.system.sr6forge?.essenceByRating?.length
                ? item.system.sr6forge.essenceByRating.join(" / ")
                : (item.system.essence || "")}
            </td>
            <td className="cell-ref">p. {item.meta.page}</td>
            <td><span className={`qa-chip qa-${item.meta.qaStatus}`}>{item.meta.qaStatus}</span></td>
            <td className="cell-issues">{(issueMap.get(item.id) ?? []).map((i) => i.rule).join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
