import React, { useMemo, useState } from "react";

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

export default function CategoryTable({ payload, issues, onEdit }) {
  const [sort, setSort] = useState({ key: null, dir: 1 });

  const issueMap = useMemo(() => {
    const m = new Map();
    for (const issue of issues ?? []) {
      if (issue.item_id) m.set(issue.item_id, [...(m.get(issue.item_id) ?? []), issue]);
    }
    return m;
  }, [issues]);

  const rows = useMemo(() => {
    const items = [...payload.items];
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
  }, [payload.items, sort, issueMap]);

  const toggle = (key) => setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: 1 }));
  const caret = (key) => (sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : "");

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
        {rows.map((item) => (
          <tr key={item.id} onClick={() => onEdit(item)}>
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
