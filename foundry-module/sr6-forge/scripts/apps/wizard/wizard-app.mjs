/** SR6 Forge chargen wizard — ApplicationV2 + Handlebars. The engine owns all
 *  state; the wizard renders budgets/validation and forwards user actions. */
import { MODULE_ID, SETTINGS, ACTOR_SKILLS } from "../../config.mjs";
import { chargenData } from "../../main.mjs";
import { ChargenEngine } from "../../engine/chargen-engine.mjs";
import { DraftStore } from "../../services/draft-store.mjs";
import { PackCatalog } from "../../services/pack-catalog.mjs";
import { commitCharacter } from "../../services/actor-committer.mjs";

const { ApplicationV2, HandlebarsApplicationMixin } = foundry.applications.api;
const TPL = (n) => `modules/${MODULE_ID}/templates/wizard/${n}.hbs`;

const STEPS = ["method", "priority", "metatype", "magic", "attributes",
  "skills", "qualities", "purchases", "contacts", "review"];

/** Purchase browser categories -> {domain, filter(row)} over pack indices. */
const SHOP_TABS = {
  weapons: { domain: "gear", types: ["WEAPON_FIREARMS", "WEAPON_CLOSE_COMBAT", "WEAPON_RANGED", "WEAPON_SPECIAL", "ACCESSORY", "AMMUNITION"] },
  armor: { domain: "gear", types: ["ARMOR", "ARMOR_ADDITION"] },
  electronics: { domain: "gear", types: ["ELECTRONICS", "SOFTWARE", "CYBERDECK"] },
  augments: { domain: "gear", types: ["CYBERWARE", "BIOWARE", "GENEWARE", "NANOWARE", "BIOLOGY"] },
  other: { domain: "gear", types: ["CHEMICALS", "MAGICAL", "SURVIVAL", "TOOLS", "CODEMODS"] },
  vehicles: { domain: "vehicles", types: null },
  foci: { domain: "foci", types: null },
};

let creationRulesCache = null;
async function creationRules() {
  if (!creationRulesCache) {
    const r = await fetch(`modules/${MODULE_ID}/data/creation-rules.json`);
    creationRulesCache = await r.json();
  }
  return creationRulesCache;
}

export class SR6ForgeWizard extends HandlebarsApplicationMixin(ApplicationV2) {
  static DEFAULT_OPTIONS = {
    id: "sr6-forge-wizard",
    classes: ["sr6-forge"],
    tag: "form",
    window: { title: "SR6FORGE.Wizard.Title", resizable: true },
    position: { width: 980, height: 740 },
    actions: {
      next: SR6ForgeWizard.#onNext,
      back: SR6ForgeWizard.#onBack,
      goto: SR6ForgeWizard.#onGoto,
      saveDraft: SR6ForgeWizard.#onSaveDraft,
      finalize: SR6ForgeWizard.#onFinalize,
      pickMethod: SR6ForgeWizard.#onPickMethod,
      pickMetatype: SR6ForgeWizard.#onPickMetatype,
      pickMor: SR6ForgeWizard.#onPickMor,
      adj: SR6ForgeWizard.#onAdjust,          // generic +/- spend buttons
      addQuality: SR6ForgeWizard.#onAddQuality,
      removeQuality: SR6ForgeWizard.#onRemoveQuality,
      addPurchase: SR6ForgeWizard.#onAddPurchase,
      removePurchase: SR6ForgeWizard.#onRemovePurchase,
      addPick: SR6ForgeWizard.#onAddPick,     // spells / powers / complex forms / foci
      removePick: SR6ForgeWizard.#onRemovePick,
      addContact: SR6ForgeWizard.#onAddContact,
      removeContact: SR6ForgeWizard.#onRemoveContact,
      addKnowledge: SR6ForgeWizard.#onAddKnowledge,
      removeKnowledge: SR6ForgeWizard.#onRemoveKnowledge,
      addSin: SR6ForgeWizard.#onAddSin,
      removeSin: SR6ForgeWizard.#onRemoveSin,
      shopTab: SR6ForgeWizard.#onShopTab,
    },
  };

  static PARTS = {
    frame: { template: TPL("wizard-frame") },
  };

  constructor(options = {}) {
    super(options);
    this.step = options.step ?? "method";
    this.engine = null;                       // built in _prepareContext (async data)
    this.draftId = options.draftId ?? foundry.utils.randomID();
    this.browse = { tab: "weapons", query: "" };
  }

  /* ------------------------------ context ------------------------------- */
  async _prepareContext() {
    if (!this.engine) {
      const rules = await creationRules();
      const draft = this.options.draftId ? DraftStore.load(this.options.draftId) : null;
      this.engine = draft
        ? ChargenEngine.fromDraft(draft.engineState, chargenData(), rules)
        : new ChargenEngine(chargenData(), rules);
      if (draft?.step) this.step = draft.step;
      this.engine.setRuleset(game.settings.get(MODULE_ID, SETTINGS.RULESET));
    }
    const e = this.engine;
    const budgets = e.budgets();
    const issues = e.validate().map((i) => ({
      ...i,
      message: game.i18n.format(`SR6FORGE.Validate.${i.id}`, i.params ?? {}),
    }));
    const stepCtx = await this.#stepContext(this.step, e, budgets);
    const stepHtml = await foundry.applications.handlebars.renderTemplate(
      TPL(`step-${this.step}`), { e, state: e.state, budgets, issues, ...stepCtx });
    return {
      step: this.step,
      steps: STEPS.map((s, i) => ({
        id: s, index: i + 1,
        label: game.i18n.localize(`SR6FORGE.Step.${s}`),
        active: s === this.step,
        done: STEPS.indexOf(this.step) > i,
      })),
      stepHtml,
      budgets,
      issues,
      errorCount: issues.filter((i) => i.severity === "error").length,
      isLast: this.step === "review",
      isFirst: this.step === "method",
    };
  }

  async #stepContext(step, e, budgets) {
    const data = chargenData();
    switch (step) {
      case "method":
        return {
          methods: [
            { id: "priority", label: "Priority (Core Rulebook)", enabled: true },
            { id: "sumtoten", label: "Sum-to-Ten (Core variant)", enabled: true },
            { id: "pointbuy", label: "Point Buy (Companion) — coming soon", enabled: false },
            { id: "karma", label: "Karma (Companion) — coming soon", enabled: false },
            { id: "lifepath", label: "Lifepath (Companion) — coming soon", enabled: false },
          ],
        };
      case "priority": {
        const letters = ["A", "B", "C", "D", "E"];
        const cols = ["METATYPE", "ATTRIBUTE", "MAGIC", "SKILLS", "RESOURCES"];
        const grants = (col, letter) => {
          const row = data.priorities?.[letter]?.[col];
          if (!row) return "—";
          if (col === "ATTRIBUTE") return `${row.attributePoints} attr pts`;
          if (col === "SKILLS") return `${row.skillPoints} skill pts`;
          if (col === "RESOURCES") return `${row.nuyen.toLocaleString()}¥`;
          if (col === "METATYPE") return `${Object.keys(row.metatypes).length} metatypes / ${row.adjustmentDefault} adj`;
          if (col === "MAGIC") return Object.entries(row.byMor)
            .map(([m, v]) => `${m} ${v}`).join(", ") || "mundane";
          return "—";
        };
        return {
          columns: cols.map((c) => ({
            id: c, current: e.state.priorities[c], letters,
          })),
          grid: letters.map((l) => ({
            letter: l,
            cells: cols.map((c) => ({
              column: c, text: grants(c, l),
              picked: e.state.priorities[c] === l,
            })),
          })),
        };
      }
      case "metatype":
        return { metatypes: e.legalMetatypes().map((m) => ({
          ...m, selected: m.id === e.state.metatypeId,
          maxima: Object.entries(m.attributeMaxCreation ?? {})
            .filter(([, v]) => v !== 6).map(([k, v]) => `${k.toUpperCase()} ${v}`).join(" · "),
        })) };
      case "magic": {
        const mor = data.morTypes?.[e.state.morId] ?? {};
        return {
          paths: e.legalMagicPaths().map((m) => ({
            ...m, selected: m.id === e.state.morId,
          })),
          isAspected: !!mor.aspected,
          isMysticAdept: !!(mor.powers && mor.paysPowers),
          aspectedOptions: ["sorcery", "conjuring", "enchanting"].map((s) => ({
            id: s, selected: e.state.aspectedSkill === s,
          })),
        };
      }
      case "attributes": {
        const maxima = data.metatypes?.[e.state.metatypeId]?.attributeMaxCreation ?? {};
        const mor = data.morTypes?.[e.state.morId] ?? {};
        const rows = [];
        for (const k of ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"]) {
          const max = maxima[k] ?? 6;
          rows.push({ key: k, label: k.toUpperCase(), rating: e.attrRating(k),
            max, adjusted: max !== 6,
            points: e.state.attributes[k].points, adjust: e.state.attributes[k].adjust });
        }
        const specials = [{ key: "edg", label: "EDGE", max: maxima.edg ?? 6 }];
        if (mor.magic) specials.push({ key: "mag", label: "MAGIC", max: 6 });
        if (mor.resonance) specials.push({ key: "res", label: "RESONANCE", max: 6 });
        for (const s of specials) {
          s.rating = e.attrRating(s.key);
          s.adjust = e.state.attributes[s.key].adjust;
        }
        return { rows, specials };
      }
      case "skills": {
        const skills = ACTOR_SKILLS.map((id) => {
          const def = data.skills?.[id] ?? {};
          const st = e.state.skills[id] ?? { points: 0, spec: null };
          const unlocked = !def.restricted
            || (data.morTypes?.[e.state.morId]?.skillUnlocks ?? []).includes(id);
          return { id, label: def.name ?? id, points: st.points ?? 0, spec: st.spec,
            restricted: def.restricted, locked: !unlocked,
            specs: Object.entries(def.specializations ?? {})
              .map(([sid, sp]) => ({ id: sid, label: sp.name, selected: st.spec === sid })) };
        });
        return { skills, knowledge: e.state.knowledge };
      }
      case "qualities": {
        const rows = await PackCatalog.index("qualities");
        const q = this.browse.query.toLowerCase();
        const list = rows
          .filter((r) => !q || r.name.toLowerCase().includes(q))
          .slice(0, 50)
          .map((r) => ({ uuid: r.uuid, name: r.name,
            genesisID: r.system?.genesisID,
            value: r.system?.value ?? 0, category: r.system?.category ?? "" }));
        return { list, taken: e.state.qualities.map((t) => ({
          ...t, name: t.genesisID })) , query: this.browse.query };
      }
      case "purchases": {
        const tab = SHOP_TABS[this.browse.tab] ?? SHOP_TABS.weapons;
        const rows = await PackCatalog.index(tab.domain);
        const q = this.browse.query.toLowerCase();
        const cap = 6;
        const list = rows
          .filter((r) => !tab.types || tab.types.includes(r.system?.type))
          .filter((r) => !q || r.name.toLowerCase().includes(q))
          .slice(0, 50)
          .map((r) => ({ uuid: r.uuid, name: r.name, price: r.system?.price ?? 0,
            avail: r.system?.avail ?? 0, essence: r.system?.essence ?? 0,
            itemType: r.type, overCap: (r.system?.avail ?? 0) > cap }));
        const mor = data.morTypes?.[e.state.morId] ?? {};
        const picks = {};
        for (const [kind, domain, allowed] of [
          ["spell", "spells", mor.spells],
          ["power", "adept_powers", mor.powers],
          ["complexform", "complexforms", mor.resonance],
        ]) {
          if (!allowed) continue;
          const prow = await PackCatalog.index(domain);
          picks[kind] = prow
            .filter((r) => !q || r.name.toLowerCase().includes(q))
            .slice(0, 30)
            .map((r) => ({ uuid: r.uuid, name: r.name, kind }));
        }
        return {
          tabs: Object.keys(SHOP_TABS).map((t) => ({ id: t, active: t === this.browse.tab })),
          list, picks, query: this.browse.query,
          owned: e.state.purchases,
          spells: e.state.spells, powers: e.state.powers, complexForms: e.state.complexForms,
          lifestyles: Object.entries(data.lifestyles ?? {}).map(([id, l]) => ({
            id, ...l, selected: id === e.state.lifestyleId })),
          sins: e.state.sins,
          canSpells: !!mor.spells, canPowers: !!mor.powers, canCF: !!mor.resonance,
          isMysticAdept: !!(mor.powers && mor.paysPowers),
          ppBought: e.state.powerPointsBought,
        };
      }
      case "contacts":
        return { contacts: e.state.contacts,
          archetypes: Object.entries(data.contactArchetypes ?? {})
            .map(([id, a]) => ({ id, name: a.name })) };
      case "review":
        return {
          name: e.state.name,
          conversions: e.state.conversions,
          convRate: (await creationRules()).karmaToNuyen.rate,
          plan: null,
        };
      default:
        return {};
    }
  }

  /* ------------------------------ rendering ------------------------------ */
  async _onRender(context, options) {
    await super._onRender?.(context, options);
    const root = this.element;
    // change-events (selects / inputs) that aren't click actions
    root.querySelectorAll("[data-change]").forEach((el) => {
      el.addEventListener("change", (ev) => this.#onChange(ev));
    });
    root.querySelectorAll("[data-search]").forEach((el) => {
      el.addEventListener("input", foundry.utils.debounce((ev) => {
        this.browse.query = ev.target.value;
        this.render();
      }, 250));
    });
  }

  #onChange(ev) {
    const el = ev.target;
    const kind = el.dataset.change;
    const e = this.engine;
    switch (kind) {
      case "priority": e.setPriority(el.dataset.column, el.value || null); break;
      case "spec": e.spend({ kind: "spec", target: el.dataset.skill, spec: el.value || null }); break;
      case "aspected": e.setMagicPath(e.state.morId, { aspectedSkill: el.value }); break;
      case "lifestyle": e.spend({ kind: "lifestyle", id: el.value }); break;
      case "name": e.state.name = el.value; return;      // no re-render while typing
      case "contactField": {
        const i = Number(el.dataset.index);
        e.spend({ kind: "contact", index: i,
          patch: { [el.dataset.field]: el.dataset.field === "name" ? el.value : Number(el.value) } });
        break;
      }
      default: return;
    }
    this.render();
  }

  /* ------------------------------ actions -------------------------------- */
  static #onNext() { this.#go(+1); }
  static #onBack() { this.#go(-1); }
  #go(dir) {
    const i = STEPS.indexOf(this.step);
    const next = STEPS[Math.min(STEPS.length - 1, Math.max(0, i + dir))];
    this.step = next;
    this.#autosave();
    this.render();
  }
  static #onGoto(_ev, target) {
    this.step = target.dataset.step;
    this.render();
  }

  async #autosave() {
    await DraftStore.save(this.draftId, {
      name: this.engine.state.name, step: this.step,
      engineState: this.engine.toDraft(),
    });
  }
  static async #onSaveDraft() {
    await this.#autosave();
    ui.notifications.info("SR6 Forge: draft saved.");
  }

  static #onPickMethod(_ev, target) {
    this.engine.setMethod(target.dataset.method);
    this.step = "priority";
    this.render();
  }
  static #onPickMetatype(_ev, target) {
    this.engine.setMetatype(target.dataset.metatype);
    this.render();
  }
  static #onPickMor(_ev, target) {
    this.engine.setMagicPath(target.dataset.mor,
      { aspectedSkill: this.engine.state.aspectedSkill });
    this.render();
  }

  static #onAdjust(_ev, target) {
    const d = target.dataset;
    const op = { kind: d.kind, target: d.target, delta: Number(d.delta ?? 1) };
    if (d.pool) op.pool = d.pool;
    if (d.uuid) op.uuid = d.uuid;
    const res = this.engine.spend(op);
    if (!res.ok) ui.notifications.warn(`SR6 Forge: ${res.reason}`);
    this.render();
  }

  static #onAddQuality(_ev, target) {
    const res = this.engine.spend({ kind: "quality",
      genesisID: target.dataset.genesisId });
    if (!res.ok) ui.notifications.warn(`SR6 Forge: ${res.reason}`);
    this.render();
  }
  static #onRemoveQuality(_ev, target) {
    this.engine.spend({ kind: "quality", genesisID: target.dataset.genesisId, remove: true });
    this.render();
  }

  static #onAddPurchase(_ev, target) {
    const d = target.dataset;
    this.engine.spend({ kind: "purchase", uuid: d.uuid, name: d.name,
      price: Number(d.price ?? 0), avail: Number(d.avail ?? 0),
      essence: Number(d.essence ?? 0), itemType: d.itemType, stack: true });
    this.render();
  }
  static #onRemovePurchase(_ev, target) {
    this.engine.spend({ kind: "purchase", uuid: target.dataset.uuid, remove: true });
    this.render();
  }

  static #onAddPick(_ev, target) {
    const d = target.dataset;
    const res = this.engine.spend({ kind: d.kind, uuid: d.uuid, name: d.name,
      cost: Number(d.cost ?? 0) });
    if (!res.ok) ui.notifications.warn(`SR6 Forge: ${res.reason}`);
    this.render();
  }
  static #onRemovePick(_ev, target) {
    this.engine.spend({ kind: target.dataset.kind, uuid: target.dataset.uuid, remove: true });
    this.render();
  }

  static #onAddContact() {
    this.engine.spend({ kind: "contact", name: "" });
    this.render();
  }
  static #onRemoveContact(_ev, target) {
    this.engine.spend({ kind: "contact", index: Number(target.dataset.index), remove: true });
    this.render();
  }

  static #onAddKnowledge(_ev, target) {
    const root = this.element;
    const name = root.querySelector("[name=knowledge-name]")?.value?.trim();
    const type = root.querySelector("[name=knowledge-type]")?.value ?? "knowledge";
    const native = !!root.querySelector("[name=knowledge-native]")?.checked;
    if (!name) return;
    this.engine.spend({ kind: "knowledge", name, type, native });
    this.render();
  }
  static #onRemoveKnowledge(_ev, target) {
    this.engine.spend({ kind: "knowledge", index: Number(target.dataset.index), remove: true });
    this.render();
  }

  static #onAddSin(_ev, target) {
    this.engine.spend({ kind: "sin", rating: Number(target.dataset.rating ?? 1) });
    this.render();
  }
  static #onRemoveSin(_ev, target) {
    this.engine.spend({ kind: "sin", index: Number(target.dataset.index), remove: true });
    this.render();
  }

  static #onShopTab(_ev, target) {
    this.browse.tab = target.dataset.tab;
    this.render();
  }

  static async #onFinalize() {
    const issues = this.engine.validate();
    if (issues.some((i) => i.severity === "error")) {
      ui.notifications.error("SR6 Forge: resolve all errors before creating the character.");
      return;
    }
    const plan = this.engine.commitPlan();
    try {
      const actor = await commitCharacter(plan);
      await DraftStore.delete(this.draftId);
      ui.notifications.info(`SR6 Forge: ${actor.name} created.`);
      this.close();
      actor.sheet?.render(true);
    } catch (err) {
      ui.notifications.error(`SR6 Forge: creation failed — ${err.message}`);
    }
  }
}
