export function toFoundryDoc(item) {
  if (!item?.system?.type) throw new TypeError(`item ${item?.id ?? "?"} has no system.type`);
  const system = structuredClone(item.system);
  system.description ??= "";
  system.genesisID ??= item.id;
  return {
    name: item.name,
    type: "gear",
    img: "icons/svg/item-bag.svg",
    system,
    effects: [],
    flags: {},
  };
}
