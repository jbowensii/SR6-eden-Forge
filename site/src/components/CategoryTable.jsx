import React from "react";

export default function CategoryTable({ payload, issues, onEdit }) {
  const issueMap = new Map();
  for (const issue of issues ?? []) {
    if (issue.item_id) issueMap.set(issue.item_id, [...(issueMap.get(issue.item_id) ?? []), issue]);
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Name</th><th>Subtype</th><th>Price</th><th>Avail</th><th>Ref</th><th>QA</th><th>Issues</th>
        </tr>
      </thead>
      <tbody>
        {payload.items.map((item) => (
          <tr key={item.id} onClick={() => onEdit(item)}>
            <td className="cell-name">
              {item.img && <span className="has-img" title={item.img}>◈</span>}
              {item.name}
            </td>
            <td className="cell-subtype">{item.system.subtype ?? ""}</td>
            <td className="cell-num">{item.system.priceDef || item.system.price}</td>
            <td className="cell-num">{item.system.availDef || item.system.avail}</td>
            <td className="cell-ref">p. {item.meta.page}</td>
            <td><span className={`qa-chip qa-${item.meta.qaStatus}`}>{item.meta.qaStatus}</span></td>
            <td className="cell-issues">{(issueMap.get(item.id) ?? []).map((i) => i.rule).join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
