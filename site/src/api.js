async function json(res) {
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? `HTTP ${res.status}`);
  return res.json();
}

export const getTree = () => fetch("/api/tree").then(json);
export const getTypeTree = () => fetch("/api/typetree").then(json);
export const getItems = (type, subtype) => {
  const q = subtype === undefined ? "" : `&subtype=${encodeURIComponent(subtype)}`;
  return fetch(`/api/items?type=${encodeURIComponent(type)}${q}`).then(json);
};
export const searchItems = (q) => fetch(`/api/search?q=${encodeURIComponent(q)}`).then(json);
export const getCategory = (b, d, c) => fetch(`/api/category/${b}/${d}/${c}`).then(json);
export const putItem = (b, d, c, item) =>
  fetch(`/api/item/${b}/${d}/${c}/${item.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  }).then(json);
export const deleteItem = (b, d, c, id) =>
  fetch(`/api/item/${b}/${d}/${c}/${id}`, { method: "DELETE" }).then(json);
export const validate = () => fetch("/api/validate", { method: "POST" }).then(json);
export const exportModule = (book, domain, status) =>
  fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ book, domain, status }),
  }).then(json);
export const getBooks = () => fetch("/api/books").then(json);
export const getBookImages = (book) => fetch(`/api/bookimages/${book}`).then(json);
export const assignRender = (payload) =>
  fetch("/api/assign-render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(json);
export const searchIcons = (q) => fetch(`/api/icons?q=${encodeURIComponent(q)}`).then(json);
export const assignIcon = (payload) =>
  fetch("/api/icon/assign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(json);
