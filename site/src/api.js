async function json(res) {
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? `HTTP ${res.status}`);
  return res.json();
}

export const getTree = () => fetch("/api/tree").then(json);
export const getCategory = (b, d, c) => fetch(`/api/category/${b}/${d}/${c}`).then(json);
export const putItem = (b, d, c, item) =>
  fetch(`/api/item/${b}/${d}/${c}/${item.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  }).then(json);
export const validate = () => fetch("/api/validate", { method: "POST" }).then(json);
