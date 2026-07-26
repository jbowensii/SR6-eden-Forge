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
          <th>Name</th><th>Subtype</th><th>Price</th><th>Avail</th><th>QA</th><th>Issues</th>
        </tr>
      </thead>
      <tbody>
        {payload.items.map((item) => (
          <tr key={item.id} onClick={() => onEdit(item)}>
            <td>{item.name}</td>
            <td>{item.system.subtype ?? ""}</td>
            <td>{item.system.priceDef ?? item.system.price}</td>
            <td>{item.system.availDef ?? item.system.avail}</td>
            <td className={`qa qa-${item.meta.qaStatus}`}>{item.meta.qaStatus}</td>
            <td>{(issueMap.get(item.id) ?? []).map((i) => i.rule).join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
