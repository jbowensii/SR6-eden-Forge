/** Karma advancement for an existing eden Player.
 *
 *  Same split as the wizard: advancement-engine.mjs prices and describes every
 *  operation, this only renders and applies. Each purchase is confirmed, then
 *  written as one actor.update plus one ledger entry, so undo can replay the
 *  captured `before` values.
 */
import { MODULE_ID, ACTOR_SKILLS } from "../../config.mjs";
import { chargenData } from "../../main.mjs";
import { preview, applyPatch, undoPatch, snapshot } from "../../engine/advancement-engine.mjs";
import { Ledger } from "../../services/ledger.mjs";
import { PackCatalog } from "../../services/pack-catalog.mjs";

const { ApplicationV2, HandlebarsApplicationMixin } = foundry.applications.api;
const TPL = (n) => `modules/${MODULE_ID}/templates/advancement/${n}.hbs`;

const CORE_ATTRS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"];

let rulesCache = null;
async function creationRules() {
  if (!rulesCache) rulesCache = await (await fetch(`modules/${MODULE_ID}/data/creation-rules.json`)).json();
  return rulesCache;
}

export class SR6AdvancementApp extends HandlebarsApplicationMixin(ApplicationV2) {
  static DEFAULT_OPTIONS = {
    id: "sr6-forge-advancement",
    classes: ["sr6-forge"],
    window: { title: "SR6 Forge — Advancement", resizable: true },
    position: { width: 860, height: 720 },
    actions: {
      buy: SR6AdvancementApp.#onBuy,
      undo: SR6AdvancementApp.#onUndo,
      tab: SR6AdvancementApp.#onTab,
    },
  };

  static PARTS = { body: { template: TPL("advancement") } };

  constructor(options = {}) {
    super(options);
    this.actor = options.actor;
    this.tab = "attributes";
  }

  get title() { return `SR6 Forge — ${this.actor?.name ?? "Advancement"}`; }

  async _prepareContext() {
    const actor = this.actor;
    const rules = await creationRules();
    const data = chargenData();
    const snap = snapshot(actor);
    const mor = data.morTypes?.[snap.mortype] ?? {};

    const price = (op) => preview(op, snap, rules, { data });

    const attributes = [...CORE_ATTRS, "edg"]
      .concat(mor.magic ? ["mag"] : [])
      .concat(mor.resonance ? ["res"] : [])
      .filter((k) => snap.attributes[k])
      .map((k) => ({ key: k, label: k.toUpperCase(), ...price({ kind: "raiseAttribute", target: k }) }));

    const skills = ACTOR_SKILLS.map((id) => {
      const def = data.skills?.[id] ?? {};
      const name = def.name ?? id;
      const sk = snap.skills[id] ?? { points: 0, specialization: "", expertise: "" };
      return {
        id, name, points: sk.points,
        specialization: sk.specialization, expertise: sk.expertise,
        raise: price({ kind: "raiseSkill", target: id, name }),
        specs: Object.entries(def.specializations ?? {})
          .map(([sid, sp]) => ({ id: sid, label: sp.name }))
          .sort((a, b) => a.label.localeCompare(b.label)),
        specCost: rules.karmaCosts.specialization,
        expertiseCost: rules.karmaCosts.expertise,
        canSpec: sk.points > 0 && !sk.specialization,
        canExpertise: !!sk.specialization && !sk.expertise,
      };
    }).sort((a, b) => a.name.localeCompare(b.name));

    const magic = [];
    const learnable = [];
    if (mor.magic || mor.resonance) {
      magic.push({ ...price({ kind: "initiate" }), kind: "initiate" });
      // what this character may still learn, minus what they already know
      const known = new Set(actor.items.map((i) => i.system?.genesisID).filter(Boolean));
      for (const [op, domain, label, allowed] of [
        ["learnSpell", "spells", "Spells", mor.spells],
        ["learnRitual", "rituals", "Rituals", mor.spells],
        ["learnComplexForm", "complexforms", "Complex Forms", mor.resonance],
      ]) {
        if (!allowed) continue;
        const rows = await PackCatalog.index(domain);
        learnable.push({
          op, label,
          cost: price({ kind: op, name: label }).karma,
          list: rows
            .filter((r) => !known.has(r.system?.genesisID))
            .sort((a, b) => a.name.localeCompare(b.name))
            .slice(0, 300)
            .map((r) => ({ uuid: r.uuid, name: r.name })),
        });
      }
    }

    return {
      actorName: actor.name,
      karma: snap.karma, karmaTotal: snap.karmaTotal,
      nuyen: snap.nuyen,
      tab: this.tab,
      tabs: [
        { id: "attributes", label: "Attributes", active: this.tab === "attributes" },
        { id: "skills", label: "Skills", active: this.tab === "skills" },
        { id: "magic", label: "Magic / Resonance", active: this.tab === "magic",
          enabled: !!(mor.magic || mor.resonance) },
        { id: "ledger", label: "Ledger", active: this.tab === "ledger" },
      ],
      attributes, skills, magic, learnable,
      convertRate: rules.karmaToNuyen.rate,
      convert: price({ kind: "karmaToNuyen", karma: 1 }),
      ledger: Ledger.entries(actor).map((e, i, all) => ({
        ...e, last: i === all.length - 1,
      })).reverse(),
      ledgerSpent: Ledger.spent(actor),
    };
  }

  async _onRender() {
    for (const el of this.element.querySelectorAll("[data-change]")) {
      el.addEventListener("change", (ev) => this.#onChange(ev));
    }
  }

  #onChange(ev) {
    const el = ev.currentTarget;
    if (el.dataset.change === "specValue") {
      this.pendingSpec = { skill: el.dataset.skill, value: el.value };
    }
  }

  /** Price, confirm, apply, record. One update + one ledger entry. */
  async #purchase(op) {
    const rules = await creationRules();
    const snap = snapshot(this.actor);
    const pv = preview(op, snap, rules, { data: chargenData() });
    if (!pv.ok) {
      ui.notifications.warn(`SR6 Forge: ${pv.reason ?? "not allowed"}`);
      return;
    }
    const confirmed = await foundry.applications.api.DialogV2.confirm({
      window: { title: "Confirm advancement" },
      content: `<p>${pv.label}</p><p><b>${pv.karma} karma</b> — you have ${snap.karma}.</p>`,
    });
    if (!confirmed) return;

    const patch = applyPatch(pv, snap);
    const before = Ledger.captureBefore(this.actor, pv.patch ?? {});
    before["system.karma"] = snap.karma;

    let embeddedId = null;
    try {
      if (pv.embed) {
        const doc = await fromUuid(pv.embed);
        if (!doc) throw new Error(`item not found: ${pv.embed}`);
        const [created] = await this.actor.createEmbeddedDocuments("Item", [doc.toObject()]);
        embeddedId = created?.id ?? null;
      }
      if (pv.removeItemId) await this.actor.deleteEmbeddedDocuments("Item", [pv.removeItemId]);
      await this.actor.update(patch);
    } catch (err) {
      // roll the embed back so the ledger never records a half-applied buy
      if (embeddedId) await this.actor.deleteEmbeddedDocuments("Item", [embeddedId]).catch(() => {});
      ui.notifications.error(`SR6 Forge: advancement failed — ${err.message}`);
      return;
    }

    await Ledger.append(this.actor, {
      ts: Date.now(), op: op.kind, label: pv.label,
      karma: pv.karma, nuyen: pv.nuyen ?? 0,
      from: pv.from ?? null, to: pv.to ?? null,
      before, embeddedId,
    });
    this.render();
  }

  /* ------------------------------- actions ------------------------------- */
  static async #onBuy(_ev, t) {
    const d = t.dataset;
    const op = { kind: d.op, target: d.target, name: d.name };
    if (d.op === "addSpecialization" || d.op === "addExpertise") {
      const sel = this.element.querySelector(`[data-change="specValue"][data-skill="${d.target}"]`);
      const value = d.value || sel?.value;
      if (!value) { ui.notifications.warn("SR6 Forge: pick a specialization first."); return; }
      op.value = value;
    }
    if (d.op === "karmaToNuyen") op.karma = Number(d.karma ?? 1);
    if (d.uuid) op.uuid = d.uuid;
    await this.#purchase(op);
  }

  static async #onUndo() {
    const entries = Ledger.entries(this.actor);
    const last = entries[entries.length - 1];
    if (!last) return;
    const confirmed = await foundry.applications.api.DialogV2.confirm({
      window: { title: "Undo advancement" },
      content: `<p>Undo <b>${last.label}</b> and refund ${last.karma} karma?</p>`,
    });
    if (!confirmed) return;

    const snap = snapshot(this.actor);
    await this.actor.update(undoPatch(last, snap));
    if (last.embeddedId) {
      await this.actor.deleteEmbeddedDocuments("Item", [last.embeddedId]).catch(() => {});
    }
    await Ledger.popLast(this.actor);
    this.render();
  }

  static #onTab(_ev, t) { this.tab = t.dataset.tab; this.render(); }
}
