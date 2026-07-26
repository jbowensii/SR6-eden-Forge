export function toFoundryDoc(item, { product } = {}) {
  if (!item?.system?.type) throw new TypeError(`item ${item?.id ?? "?"} has no system.type`);
  const system = structuredClone(item.system);
  system.description ??= "";
  system.genesisID ??= item.id;
  // reference location: book title + printed page travel with the document
  system.product ??= product ?? item.meta?.book ?? "";
  system.page ??= item.meta?.page ?? 0;
  return {
    name: item.name,
    type: "gear",
    img: item.img || "icons/svg/item-bag.svg",
    system,
    effects: [],
    flags: {},
  };
}
