/** SR6 Forge chargen wizard — ApplicationV2 + Handlebars.
 *  The engine owns all state; this renders budgets/validation and forwards
 *  actions. Layout mirrors Commlink6's editor: nav rail | working pane |
 *  detail pane, with available/chosen lists per section. */
import { MODULE_ID, SETTINGS, ACTOR_SKILLS } from "../../config.mjs";
import { chargenData } from "../../main.mjs";
import { ChargenEngine } from "../../engine/chargen-engine.mjs";
import { POINT_BUY, LIFEPATH_ADULT_COUNT } from "../../engine/providers.mjs";
import { qualityKarma, ruleConst } from "../../engine/budgets.mjs";
import { DraftStore } from "../../services/draft-store.mjs";
import { PackCatalog } from "../../services/pack-catalog.mjs";
import { commitCharacter } from "../../services/actor-committer.mjs";

const { ApplicationV2, HandlebarsApplicationMixin } = foundry.applications.api;
const TPL = (n) => `modules/${MODULE_ID}/templates/wizard/${n}.hbs`;
const renderTpl = (p, d) => foundry.applications.handlebars.renderTemplate(p, d);

const STEPS = ["method", "priority", "metatype", "magic", "attributes",
  "skills", "qualities", "purchases", "contacts", "review"];
/** The second step is method-specific: priorities, a CP ledger, a karma pool
 *  or the life path. One step slot, four templates. */
const BUILD_TEMPLATE = {
  priority: "priority", sumtoten: "priority",
  pointbuy: "pointbuy", karma: "karmabuild", lifepath: "lifepath",
};
const BUILD_LABEL = {
  priority: "Priorities", sumtoten: "Priorities",
  pointbuy: "Character Points", karma: "Karma Pool", lifepath: "Life Path",
};

const STEP_LABEL = {
  method: "Method", priority: "Priorities", metatype: "Metatype",
  magic: "Magic / Res", attributes: "Attributes", skills: "Skills",
  qualities: "Qualities", purchases: "Gear & Magic", contacts: "Contacts",
  review: "Review",
};

/** Shop tabs: which gear types belong where (organised like Commlink sections). */
const SHOP_TABS = [
  { id: "weapons",   label: "Weapons",   domain: "gear", types: ["WEAPON_FIREARMS", "WEAPON_CLOSE_COMBAT", "WEAPON_RANGED", "WEAPON_SPECIAL", "WEAPON_VEHICLE"] },
  { id: "ammo",      label: "Ammo",      domain: "gear", types: ["AMMUNITION"] },
  // ACCESSORY is far more than weapon mods (armour, cyberlimb, vision,
  // electronics), so it gets its own tab and leans on the category dropdown.
  { id: "accessories", label: "Accessories", domain: "gear", types: ["ACCESSORY"] },
  { id: "armor",     label: "Armor",     domain: "gear", types: ["ARMOR", "ARMOR_ADDITION"] },
  { id: "matrix",    label: "Matrix",    domain: "gear", types: ["ELECTRONICS", "SOFTWARE", "CYBERDECK", "CODEMODS"] },
  { id: "augments",  label: "Augments",  domain: "gear", types: ["CYBERWARE", "BIOWARE", "GENEWARE", "NANOWARE", "BIOLOGY"] },
  { id: "gear",      label: "Gear",      domain: "gear", types: ["CHEMICALS", "MAGICAL", "SURVIVAL", "TOOLS"] },
  { id: "vehicles",  label: "Vehicles",  domain: "vehicles", types: null },
  { id: "foci",      label: "Foci",      domain: "foci", types: null },
  { id: "magic",     label: "Magic",     magic: true },
  { id: "lifestyle", label: "Lifestyle & SIN", lifestyle: true },
];

/** Rows rendered per browser list. The query narrows before this cap applies. */
const ROW_CAP = 400;

let rulesCache = null;
async function creationRules() {
  if (!rulesCache) rulesCache = await (await fetch(`modules/${MODULE_ID}/data/creation-rules.json`)).json();
  return rulesCache;
}

export class SR6ForgeWizard extends HandlebarsApplicationMixin(ApplicationV2) {
  static DEFAULT_OPTIONS = {
    id: "sr6-forge-wizard",
    classes: ["sr6-forge"],
    window: { title: "SR6 Forge — Character Generation", resizable: true },
    position: { width: 1120, height: 780 },
    actions: {
      next: SR6ForgeWizard.#onNext,
      back: SR6ForgeWizard.#onBack,
      goto: SR6ForgeWizard.#onGoto,
      saveDraft: SR6ForgeWizard.#onSaveDraft,
      finalize: SR6ForgeWizard.#onFinalize,
      toggleIssues: SR6ForgeWizard.#onToggleIssues,
      pickMethod: SR6ForgeWizard.#onPickMethod,
      pickMetatype: SR6ForgeWizard.#onPickMetatype,
      pickMor: SR6ForgeWizard.#onPickMor,
      adj: SR6ForgeWizard.#onAdjust,
      addQuality: SR6ForgeWizard.#onAddQuality,
      removeQuality: SR6ForgeWizard.#onRemoveQuality,
      addPurchase: SR6ForgeWizard.#onAddPurchase,
      removePurchase: SR6ForgeWizard.#onRemovePurchase,
      addPick: SR6ForgeWizard.#onAddPick,
      removePick: SR6ForgeWizard.#onRemovePick,
      addContact: SR6ForgeWizard.#onAddContact,
      removeContact: SR6ForgeWizard.#onRemoveContact,
      addKnowledge: SR6ForgeWizard.#onAddKnowledge,
      removeKnowledge: SR6ForgeWizard.#onRemoveKnowledge,
      addSin: SR6ForgeWizard.#onAddSin,
      removeSin: SR6ForgeWizard.#onRemoveSin,
      shopTab: SR6ForgeWizard.#onShopTab,
      addModule: SR6ForgeWizard.#onAddModule,
      removeModule: SR6ForgeWizard.#onRemoveModule,
    },
  };

  static PARTS = { frame: { template: TPL("wizard-frame") } };

  constructor(options = {}) {
    super(options);
    this.step = "method";
    this.engine = null;
    this.draftId = options.draftId ?? foundry.utils.randomID();
    this.ui = { shopTab: "weapons", shopSubtype: "", qualityFilter: "all",
      query: {}, issuesOpen: false };
    this.detail = null;
    this._scroll = {};
    this._detailCache = new Map();
  }

  /* =============================== context ================================ */
  async _prepareContext() {
    if (!this.engine) {
      const rules = await creationRules();
      const draft = this.options.draftId ? DraftStore.load(this.options.draftId) : null;
      this.engine = draft
        ? ChargenEngine.fromDraft(draft.engineState, chargenData(), rules)
        : new ChargenEngine(chargenData(), rules);
      if (draft?.step) this.step = draft.step;
      if (!draft) this.engine.setRuleset(game.settings.get(MODULE_ID, SETTINGS.RULESET));
      // world optional-rule overrides always apply (they may have changed
      // since a draft was saved)
      this.engine.setOptionalRules(game.settings.get(MODULE_ID, SETTINGS.OPTIONAL_RULES));
    }
    const e = this.engine;
    const budgets = e.budgets();
    const issues = e.validate().map((i) => ({
      ...i,
      message: game.i18n.format(`SR6FORGE.Validate.${i.id}`, i.params ?? {}),
    }));
    const errsByStep = {};
    for (const i of issues) {
      if (i.severity === "error") errsByStep[i.step] = (errsByStep[i.step] ?? 0) + 1;
    }
    const tplName = this.step === "priority"
      ? `step-${BUILD_TEMPLATE[e.state.method] ?? "priority"}` : `step-${this.step}`;
    const stepHtml = await renderTpl(TPL(tplName),
      await this.#stepContext(this.step, e, budgets, issues));

    const errorCount = issues.filter((i) => i.severity === "error").length;
    return {
      step: this.step,
      steps: STEPS.map((s, i) => ({
        id: s, index: i + 1,
        label: s === "priority" ? (BUILD_LABEL[e.state.method] ?? STEP_LABEL[s]) : STEP_LABEL[s],
        active: s === this.step, done: STEPS.indexOf(this.step) > i,
        errors: errsByStep[s] ?? 0,
      })),
      stepHtml,
      chips: this.#chips(budgets),
      issues, errorCount, warnCount: issues.length - errorCount,
      manyErrors: errorCount !== 1,
      issuesOpen: this.ui.issuesOpen,
      detail: this.detail,
      isLast: this.step === "review",
      isFirst: this.step === "method",
    };
  }

  #chips(b) {
    const mk = (k, o, title, alwaysShow = true) => {
      if (!alwaysShow && !o.max) return null;
      return { k, v: o.left, m: o.max, title,
        cls: o.left < 0 ? "over" : (o.left === 0 ? "good" : "") };
    };
    const out = [
      b.characterPoints ? mk("CP", b.characterPoints, "Character points") : null,
      mk("ATTR", b.attributePoints, "Attribute points"),
      mk("ADJ", b.adjustmentPoints, "Adjustment points"),
      mk("SKILL", b.skillPoints, "Skill points"),
      mk("KNOW", b.knowledgePoints, "Knowledge points"),
      mk("KARMA", b.karma, "Karma"),
      { k: "NUYEN", v: `${b.nuyen.left.toLocaleString()}¥`, m: null,
        title: "Nuyen", cls: b.nuyen.left < 0 ? "over" : "" },
      { k: "ESS", v: b.essence.left.toFixed(2), m: null, title: "Essence",
        cls: b.essence.left <= 0 ? "over" : "" },
      mk("PP", b.powerPoints, "Power points", false),
      mk("CON", b.contactPoints, "Contact points"),
    ];
    return out.filter(Boolean);
  }

  /* ------------------- method-specific build steps ----------------------- */

  /** Point Buy — Companion p28-29. Each pool is a CP-priced stepper. */
  #pointBuyContext(e, budgets, data) {
    const st = e.state;
    const cp = budgets.characterPoints ?? { max: 0, spent: 0, left: 0 };
    const c = POINT_BUY.cost;
    const ppPrice = st.morId === "mysticadept" ? c.mysticPowerPoint : c.powerPoint;
    const mor = data.morTypes?.[st.morId] ?? {};
    const pools = [
      { id: "attribute", label: "Attribute points", price: c.attribute,
        free: POINT_BUY.free.attribute, cap: POINT_BUY.max.attribute,
        bought: st.cp.attribute, total: budgets.attributePoints.max,
        note: `${POINT_BUY.free.attribute} free, up to ${POINT_BUY.max.attribute} more at ${c.attribute} CP each` },
      { id: "skill", label: "Skill points", price: c.skill,
        free: POINT_BUY.free.skill, cap: POINT_BUY.max.skill,
        bought: st.cp.skill, total: budgets.skillPoints.max,
        note: `${POINT_BUY.free.skill} free, up to ${POINT_BUY.max.skill} more at ${c.skill} CP each` },
      { id: "adjustment", label: "Adjustment points", price: c.adjustment,
        free: POINT_BUY.free.adjustment, cap: POINT_BUY.max.adjustment,
        bought: st.cp.adjustment, total: budgets.adjustmentPoints.max,
        note: `1 free, up to ${POINT_BUY.max.adjustment} more at ${c.adjustment} CP each` },
      { id: "resources", label: "Resources", price: 1,
        free: 0, cap: POINT_BUY.max.nuyen / POINT_BUY.nuyenPerCp,
        bought: st.cp.resources, total: budgets.nuyen.max,
        valueText: `${budgets.nuyen.max.toLocaleString()}¥`,
        note: `${POINT_BUY.free.nuyen.toLocaleString()}¥ free, then ${POINT_BUY.nuyenPerCp.toLocaleString()}¥ per CP (max ${POINT_BUY.max.nuyen.toLocaleString()}¥)` },
    ];
    if (mor.powers) {
      pools.push({ id: "powerPoints", label: "Adept power points", price: ppPrice,
        free: 0, cap: e.attrRating("mag"), bought: st.cp.powerPoints,
        total: st.cp.powerPoints,
        note: `${ppPrice} CP each, no more than your final Magic (${e.attrRating("mag")})` });
    }
    if (mor.spells) {
      pools.push({ id: "spells", label: "Spells / rituals bought with CP", price: c.spell,
        free: 0, cap: e.attrRating("mag") * 2, bought: st.cp.spells, total: st.cp.spells,
        note: `${c.spell} CP each (or 5 karma), up to Magic x 2` });
    }
    if (mor.resonance) {
      pools.push({ id: "complexForms", label: "Complex forms bought with CP", price: c.complexForm,
        free: 0, cap: e.attrRating("res") * 2, bought: st.cp.complexForms, total: st.cp.complexForms,
        note: `${c.complexForm} CP each (or 5 karma), up to Resonance x 2` });
    }
    for (const pool of pools) pool.cpCost = pool.bought * pool.price;
    return {
      cp, pools,
      morCost: st.morId && st.morId !== "mundane" ? POINT_BUY.awakened : 0,
      morName: mor.name ?? "Mundane",
      hint: "100 character points, and every one of them must be spent. Your "
        + "metatype costs no CP — its karma comes out of the usual 50.",
      unspent: cp.left,
      over: cp.left < 0,
    };
  }

  /** Karma build — see the provenance note in providers.mjs. */
  #karmaBuildContext(e, budgets, data, rules) {
    const st = e.state;
    const mor = data.morTypes?.[st.morId] ?? {};
    const mt = data.metatypes?.[st.metatypeId];
    return {
      karma: budgets.karma,
      startKarma: e.provider.startingKarma(rules),
      rows: [
        { label: "Metatype", value: mt?.name ?? "—", karma: mt?.karma ?? 0 },
        { label: "Magic / Resonance", value: mor.name ?? "Mundane", karma: mor.karmaCost ?? 0 },
        { label: "Attributes", value: "5 x new rating, per rank", karma: null },
        { label: "Skills", value: "5 x new rank, per rank", karma: null },
        { label: "Nuyen", value: `${rules.karmaToNuyen.rate.toLocaleString()}¥ per karma`, karma: null },
      ],
      unverified: true,
      hint: "Everything is priced in karma. This method is not in any English "
        + "rulebook we own — the numbers come from the Commlink6 1.14.0 "
        + "implementation and can be changed on the optional-rules screen.",
    };
  }

  /** Life modules — Companion p31-48. */
  #lifepathContext(e, budgets, data) {
    const st = e.state;
    const modules = data.lifepathModules ?? {};
    const taken = (st.lifepath ?? []).map((pick, index) => {
      const mod = modules[pick.id] ?? {};
      return {
        index, id: pick.id, name: mod.name ?? pick.id,
        grants: this.#grantText(mod.grants),
        // "+1 to Edge, Sorcery, or Enchanting" needs the player to say which
        choices: (mod.choices ?? []).map((c, i) => ({
          i, text: c.text, mixed: c.kind === "mixed",
          picked: pick.choices?.[i] ?? "",
          options: c.options.map((o) => ({
            id: o,
            label: o.startsWith("nuyen:")
              ? `${Number(o.slice(6)).toLocaleString()}¥`
              : o.replaceAll("_", " "),
            selected: pick.choices?.[i] === o })),
        })).filter((c) => c.mixed),
      };
    });
    const available = e.provider.available(st);
    return {
      opening: e.provider.opening(),
      taken, needed: LIFEPATH_ADULT_COUNT, chosen: taken.length,
      complete: taken.length === LIFEPATH_ADULT_COUNT,
      available: available.slice(0, ROW_CAP).map((m) => ({
        id: m.id, name: m.name, page: m.page ?? "", taken: m.taken,
        requires: m.requires ?? "",
        grants: this.#grantText(m.grants),
        knowledge: m.knowledgeSkills ?? 0,
      })),
      query: this.ui.query.lifepath ?? "",
      empty: !available.length,
      hint: `The three opening modules are fixed. Then take exactly `
        + `${LIFEPATH_ADULT_COUNT} adult modules — Charisma grants no contact `
        + `points on this path, and knowledge skills come from the modules `
        + `rather than from Logic.`,
    };
  }

  #grantText(g) {
    if (!g) return "";
    const bits = [];
    if (g.attributePoints) bits.push(`${g.attributePoints} attr`);
    if (g.skillPoints) bits.push(`${g.skillPoints} skill`);
    if (g.adjustmentPoints) bits.push(`${g.adjustmentPoints} adj`);
    if (g.nuyen) bits.push(`${g.nuyen.toLocaleString()}¥`);
    if (g.contactPoints) bits.push(`${g.contactPoints} contact`);
    return bits.join(" · ");
  }

  /* ------------------------------ per step ------------------------------- */
  async #stepContext(step, e, budgets, issues) {
    const data = chargenData();
    const rules = await creationRules();
    const st = e.state;
    const q = (k) => (this.ui.query[k] ?? "");
    // The rendered list is capped, so the query has to narrow the FULL set
    // before the cap — a DOM-only filter can never reveal a row past the cap.
    const match = (k) => {
      const needle = q(k).trim().toLowerCase();
      return needle ? (r) => (r.name ?? "").toLowerCase().includes(needle) : () => true;
    };

    switch (step) {
      case "method": {
        const desc = {
          priority: "The regular generation system from the Core rules.",
          sumtoten: "Modified priority system — assign any letters whose values total ten.",
          pointbuy: "Highly customised builds by spending character points (Companion).",
          karma: "Everything priced in karma (Companion, German rules).",
          lifepath: "Build a history: childhood, adolescence and adult modules grant your traits.",
        };
        return {
          methods: ["priority", "sumtoten", "pointbuy", "karma", "lifepath"].map((id) => ({
            id, label: { priority: "Priority System", sumtoten: "Sum to Ten System",
              pointbuy: "Point Buy System", karma: "Karma System", lifepath: "Life Path System" }[id],
            desc: desc[id],
            enabled: ["priority", "sumtoten"].includes(id),
            active: st.method === id,
          })),
          rulesets: Object.keys(data.rules ?? {}).filter((r) => !r.endsWith("_de")).map((id) => ({
            id, name: { core: "Core Rulebook", core_seattle: "Standard (Seattle)",
              srm: "Shadowrun Missions", houserules: "House Rules" }[id] ?? id,
            selected: st.rulesetId === id,
          })),
        };
      }

      case "priority": {
        // one step slot, four methods — dispatch to the method's own context
        if (st.method === "pointbuy") return this.#pointBuyContext(e, budgets, data);
        if (st.method === "karma") return this.#karmaBuildContext(e, budgets, data, rules);
        if (st.method === "lifepath") return this.#lifepathContext(e, budgets, data);
        const letters = ["A", "B", "C", "D", "E"];
        const cols = [
          { id: "METATYPE", label: "Metatype" }, { id: "ATTRIBUTE", label: "Attributes" },
          { id: "MAGIC", label: "Magic/Res" }, { id: "SKILLS", label: "Skills" },
          { id: "RESOURCES", label: "Resources" },
        ];
        const grants = (col, letter) => {
          const row = data.priorities?.[letter]?.[col];
          if (!row) return "—";
          if (col === "ATTRIBUTE") return `${row.attributePoints} points`;
          if (col === "SKILLS") return `${row.skillPoints} points`;
          if (col === "RESOURCES") return `${row.nuyen.toLocaleString()}¥`;
          if (col === "METATYPE") return `${Object.keys(row.metatypes).length} metatypes · ${row.adjustmentDefault} adj`;
          if (col === "MAGIC") {
            const by = row.byMor ?? {};
            return Object.keys(by).length
              ? Object.entries(by).map(([m, v]) => `${data.morTypes?.[m]?.name ?? m} ${v}`).join(", ")
              : "mundane only";
          }
          return "—";
        };
        const val = { A: 4, B: 3, C: 2, D: 1, E: 0 };
        const total = Object.values(st.priorities).filter(Boolean)
          .reduce((n, l) => n + val[l], 0);
        return {
          methodHint: st.method === "sumtoten"
            ? "Assign any letters — their values (A=4 … E=0) must total ten or less."
            : "Assign each column a different letter, A through E.",
          sumInfo: st.method === "sumtoten" ? `Current total: ${total} / 10` : null,
          columns: cols.map((c) => ({ ...c, current: st.priorities[c.id] })),
          letters,
          grid: letters.map((l) => ({
            letter: l,
            cells: cols.map((c) => ({ text: grants(c.id, l), picked: st.priorities[c.id] === l })),
          })),
        };
      }

      case "metatype":
        return {
          letter: st.priorities.METATYPE ?? "—",
          query: q("metatype"),
          metatypes: e.legalMetatypes().map((m) => ({
            id: m.id, name: m.name, adjustmentPoints: m.adjustmentPoints,
            karma: m.karma || 0, variantOf: m.variantOf,
            selected: m.id === st.metatypeId,
            maxima: Object.entries(m.attributeMaxCreation ?? {})
              .filter(([k, v]) => v !== 6)
              .map(([k, v]) => `${k.toUpperCase()} ${v}`).join(" · "),
          })),
        };

      case "magic": {
        const mor = data.morTypes?.[st.morId] ?? {};
        return {
          letter: st.priorities.MAGIC ?? "—",
          paths: e.legalMagicPaths().map((m) => ({
            id: m.id, name: m.name, rating: m.rating,
            selected: m.id === st.morId,
            unlockText: (m.skillUnlocks ?? []).map((s) => data.skills?.[s]?.name ?? s).join(", "),
          })),
          isAspected: !!mor.aspected,
          aspectedOptions: (rules.aspectedPickOne.options ?? []).map((s) => ({
            id: s, label: data.skills?.[s]?.name ?? s, selected: st.aspectedSkill === s })),
          isMysticAdept: !!(mor.powers && mor.paysPowers),
          ppCost: rules.mysticAdeptPowerPoints.karmaPerPoint,
          ppBought: st.powerPointsBought,
        };
      }

      case "attributes": {
        const maxima = data.metatypes?.[st.metatypeId]?.attributeMaxCreation ?? {};
        const mor = data.morTypes?.[st.morId] ?? {};
        const rows = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"].map((k) => {
          const max = maxima[k] ?? 6;
          const rating = e.attrRating(k);
          return { key: k, label: k.toUpperCase(), rating, max,
            atMax: rating >= max, adjustable: max !== 6,
            points: st.attributes[k].points, adjust: st.attributes[k].adjust,
            karma: st.attributes[k].karma ?? 0 };
        });
        const specials = [{ key: "edg", label: "EDGE", sub: `max ${maxima.edg ?? 6}` }];
        if (mor.magic) specials.push({ key: "mag", label: "MAGIC", sub: "from priority" });
        if (mor.resonance) specials.push({ key: "res", label: "RESONANCE", sub: "from priority" });
        for (const s of specials) {
          s.rating = e.attrRating(s.key);
          s.adjust = st.attributes[s.key].adjust;
        }
        return { rows, specials,
          karmaHint: `Karma ranks cost ${rules.karmaCosts.attributePerRank} x the new rating, per rank — ${budgets.karma.left} karma left.` };
      }

      case "skills": {
        const unlocks = new Set(data.morTypes?.[st.morId]?.skillUnlocks ?? []);
        const skills = ACTOR_SKILLS.map((id) => {
          const def = data.skills?.[id] ?? {};
          const s = st.skills[id] ?? { points: 0, karma: 0, spec: null };
          return { id, label: def.name ?? id, points: s.points ?? 0,
            karma: s.karma ?? 0, rank: (s.points ?? 0) + (s.karma ?? 0),
            restricted: !!def.restricted, locked: !!def.restricted && !unlocks.has(id),
            specs: Object.entries(def.specializations ?? {})
              .map(([sid, sp]) => ({ id: sid, label: sp.name, selected: s.spec === sid }))
              .sort((a, b) => a.label.localeCompare(b.label)) };
        }).sort((a, b) => a.label.localeCompare(b.label));
        return { skills, query: q("skill"), knowledge: st.knowledge,
          skillKarmaHint: `Ranks can also be bought with karma (${rules.karmaCosts.skillPerRank} x the new rank) — ${budgets.karma.left} karma left.`,
          knowledgeHint: `${budgets.knowledgePoints.left} of ${budgets.knowledgePoints.max} knowledge points left (free points equal your Logic; a native language is free).` };
      }

      case "qualities": {
        const rows = await PackCatalog.index("qualities");
        const filter = this.ui.qualityFilter;
        const hits = rows
          .filter((r) => filter === "all" || (r.system?.category ?? "") === filter)
          .filter(match("quality"))
          .sort((a, b) => a.name.localeCompare(b.name));
        const list = hits
          .slice(0, ROW_CAP)
          .map((r) => ({ uuid: r.uuid, name: r.name,
            genesisID: r.system?.genesisID ?? "",
            value: r.system?.value ?? 0, category: r.system?.category ?? "" }));
        const meta = data.qualityMeta ?? {};
        const qk = qualityKarma(st, data);
        return {
          list, query: q("quality"), filter,
          listTotal: hits.length, truncated: Math.max(0, hits.length - ROW_CAP),
          netCap: rules.qualityNetBonusKarmaCap.value,
          maxCount: rules.qualityMaxCount.value,
          paidCount: st.qualities.filter((x) => !x.free).length,
          posTotal: qk.pos, negTotal: qk.neg, netBonus: qk.neg - qk.pos,
          taken: st.qualities.map((qq) => {
            const m = meta[qq.genesisID] ?? {};
            const positive = qq.positive ?? m.positive ?? true;
            return { ...qq, name: qq.name ?? qq.genesisID,
              karma: Math.abs(qq.subOptionKarma ?? qq.karma ?? m.karma ?? 0) * (qq.rating ?? 1),
              sign: positive ? "−" : "+",
              note: qq.note ?? "" };
          }),
        };
      }

      case "purchases": {
        const mor = data.morTypes?.[st.morId] ?? {};
        const tabDef = SHOP_TABS.find((t) => t.id === this.ui.shopTab) ?? SHOP_TABS[0];
        const tabs = SHOP_TABS.map((t) => ({
          id: t.id, label: t.label, active: t.id === tabDef.id,
          enabled: t.magic ? !!(mor.spells || mor.powers || mor.resonance) : true,
        }));
        const cap = ruleConst("CHARGEN_MAX_AVAILABILITY", data, rules, st.rulesetId, st.optionalRules);
        const base = {
          tabs, tabLabel: tabDef.label, owned: st.purchases,
          spentText: `${budgets.nuyen.spent.toLocaleString()}¥ spent · ${budgets.nuyen.left.toLocaleString()}¥ left`,
          isMagicTab: !!tabDef.magic, isLifestyleTab: !!tabDef.lifestyle,
          query: q("shop"),
        };
        if (tabDef.magic) {
          const kinds = [];
          for (const [kind, domain, label, allowed] of [
            ["spell", "spells", "Spells", mor.spells],
            ["power", "adept_powers", "Adept Powers", mor.powers],
            ["complexform", "complexforms", "Complex Forms", mor.resonance],
            ["ritual", "rituals", "Rituals", mor.spells],
          ]) {
            if (!allowed) continue;
            const rows = await PackCatalog.index(domain);
            const chosenList = { spell: st.spells, power: st.powers,
              complexform: st.complexForms, ritual: st.rituals }[kind];
            kinds.push({ kind, label, chosen: chosenList,
              list: rows.filter(match("shop")).sort((a, b) => a.name.localeCompare(b.name)).slice(0, ROW_CAP)
                .map((r) => ({ uuid: r.uuid, name: r.name, cost: r.system?.cost ?? 0,
                  meta: kind === "power" ? `${r.system?.cost ?? 0} PP` : "" })) });
          }
          return { ...base, magicKinds: kinds };
        }
        if (tabDef.lifestyle) {
          return { ...base,
            lifestyles: Object.entries(data.lifestyles ?? {})
              .map(([id, l]) => ({ id, ...l, selected: id === st.lifestyleId })),
            sins: st.sins, sinRatings: [1, 2, 3, 4] };
        }
        const rows = await PackCatalog.index(tabDef.domain);
        const inTab = rows.filter((r) => !tabDef.types || tabDef.types.includes(r.system?.type));
        const subCounts = {};
        for (const r of inTab) {
          const s = r.system?.subtype || "—";
          subCounts[s] = (subCounts[s] ?? 0) + 1;
        }
        const sub = this.ui.shopSubtype;
        const hits = inTab
          .filter((r) => !sub || (r.system?.subtype ?? "—") === sub)
          .filter(match("shop"))
          .sort((a, b) => a.name.localeCompare(b.name));
        const list = hits
          .slice(0, ROW_CAP)
          .map((r) => ({ uuid: r.uuid, name: r.name, price: r.system?.price ?? 0,
            avail: r.system?.avail ?? 0, essence: r.system?.essence ?? 0,
            itemType: r.type, overCap: (r.system?.avail ?? 0) > cap }));
        return { ...base, list, listTotal: inTab.length,
          shown: list.length, truncated: Math.max(0, hits.length - ROW_CAP),
          subtypes: Object.entries(subCounts).sort((a, b) => a[0].localeCompare(b[0]))
            .map(([id, count]) => ({ id, count,
              label: id.replaceAll("_", " ").toLowerCase(), selected: sub === id })) };
      }

      case "contacts":
        return {
          contacts: st.contacts,
          contactHint: `Charisma x 6 = ${budgets.contactPoints.max} contact points (Connection + Loyalty), `
            + `${budgets.contactPoints.left} left. At creation neither rating may exceed `
            + `Charisma (${budgets.contactPoints.ratingCap}).`,
          ratingCap: budgets.contactPoints.ratingCap,
          // an archetype is a label, not a fixed list — the datalist suggests the
          // book's archetypes but any text is accepted
          archetypes: Object.entries(data.contactArchetypes ?? {})
            .map(([id, a]) => ({ id, name: a.name }))
            .sort((a, b) => a.name.localeCompare(b.name)),
        };

      case "review": {
        const mt = data.metatypes?.[st.metatypeId];
        const attrs = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha"]
          .map((k) => `${k.toUpperCase()} ${e.attrRating(k)}`).join(" · ");
        const trained = Object.entries(st.skills).filter(([, s]) => s.points > 0);
        return {
          name: st.name, converted: st.conversions.karmaToNuyen,
          convRate: rules.karmaToNuyen.rate, convMax: rules.karmaToNuyen.maxKarma,
          issues,
          summary: {
            metatype: mt?.name ?? "—", mor: data.morTypes?.[st.morId]?.name ?? "—",
            method: st.method, ruleset: st.rulesetId, attrs,
            skills: trained.length ? trained.map(([k, s]) => `${data.skills?.[k]?.name ?? k} ${s.points}`).join(", ") : "none",
            qualities: st.qualities.length ? st.qualities.map((x) => x.name ?? x.genesisID).join(", ") : "none",
            gear: `${st.purchases.length} items · lifestyle ${st.lifestyleId ?? "none"} · ${st.sins.length} SIN(s)`,
            magic: `${st.spells.length} spells · ${st.powers.length} powers · ${st.complexForms.length} forms`,
            contacts: st.contacts.length ? st.contacts.map((c) => `${c.name || "?"} ${c.connection}/${c.loyalty}`).join(", ") : "none",
            remaining: `${budgets.karma.left} karma · ${budgets.nuyen.left.toLocaleString()}¥ · essence ${budgets.essence.left.toFixed(2)}`,
          },
        };
      }
      default: return {};
    }
  }

  /* =============================== render ================================= */
  async _onRender(context, options) {
    await super._onRender?.(context, options);
    const root = this.element;

    // restore scroll positions (clicking must not jump panes to the top)
    for (const el of root.querySelectorAll("[data-scroll]")) {
      const key = el.dataset.scroll;
      if (this._scroll[key]) el.scrollTop = this._scroll[key];
      el.addEventListener("scroll", () => { this._scroll[key] = el.scrollTop; }, { passive: true });
    }

    // live filtering — filter the DOM, never re-render (keeps focus + caret)
    for (const input of root.querySelectorAll("[data-filter]")) {
      const key = input.dataset.filter;
      input.addEventListener("input", () => {
        this.ui.query[key] = input.value;
        this.#applyFilter(root, key, input.value);   // instant, no focus loss
        clearTimeout(this._filterTimer);
        this._filterTimer = setTimeout(() => {       // then re-cap the full set
          this._focusFilter = key;
          this.render();
        }, 350);
      });
      if (this.ui.query[key]) this.#applyFilter(root, key, this.ui.query[key]);
    }
    if (this._focusFilter) {
      const el = root.querySelector(`[data-filter="${this._focusFilter}"]`);
      if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
      this._focusFilter = null;
    }

    // change handlers
    for (const el of root.querySelectorAll("[data-change]")) {
      el.addEventListener("change", (ev) => this.#onChange(ev));
    }

    // detail pane on hover/click of anything declaring a detail source
    for (const el of root.querySelectorAll("[data-detail-kind]")) {
      el.addEventListener("pointerenter", () => this.#showDetail(el.dataset.detailKind, el.dataset.detailId));
      el.addEventListener("click", () => this.#showDetail(el.dataset.detailKind, el.dataset.detailId));
    }
  }

  #applyFilter(root, key, value) {
    const q = value.trim().toLowerCase();
    for (const scope of root.querySelectorAll(`[data-filter-scope="${key}"]`)) {
      for (const row of scope.querySelectorAll("[data-filter-text]")) {
        const hit = !q || row.dataset.filterText.toLowerCase().includes(q);
        row.style.display = hit ? "" : "none";
      }
    }
  }

  /** Detail pane: chargen-data records render instantly; compendium docs are
   *  fetched once and cached. */
  async #showDetail(kind, id) {
    if (!kind || !id) return;
    const data = chargenData();
    const cacheKey = `${kind}:${id}`;
    if (this._detailCache.has(cacheKey)) {
      this.detail = this._detailCache.get(cacheKey);
      return this.#renderDetailOnly();
    }
    let det = null;
    if (kind === "metatype") {
      const m = data.metatypes?.[id];
      if (m) det = { name: m.name, meta: `${m.book} · p${m.page || "?"}`,
        stats: [
          { k: "ADJ", v: String(m.karma ? `${m.karma} karma` : "—") },
          ...Object.entries(m.attributeMaxCreation ?? {}).filter(([, v]) => v !== 6)
            .map(([k, v]) => ({ k: k.toUpperCase(), v: `max ${v}` })),
          ...(m.racialQualityIds?.length ? [{ k: "RACIAL", v: m.racialQualityIds.join(", ") }] : []),
        ], description: "" };
    } else if (kind === "mor") {
      const m = data.morTypes?.[id];
      if (m) det = { name: m.name, meta: "magic / resonance path",
        stats: [
          { k: "SPELLS", v: m.spells ? "yes" : "no" },
          { k: "POWERS", v: m.powers ? "yes" : "no" },
          { k: "KARMA", v: String(m.karmaCost || 0) },
        ], description: m.desc ?? "" };
    } else if (kind === "skill") {
      const s = data.skills?.[id];
      if (s) det = { name: s.name, meta: `${s.type?.toLowerCase() ?? ""} · linked ${(s.attr ?? "").toUpperCase()}`,
        stats: [
          { k: "UNTRAINED", v: s.untrained ? "usable" : "no" },
          { k: "SPECS", v: String(Object.keys(s.specializations ?? {}).length) },
        ], description: "" };
    } else if (kind === "uuid") {
      try {
        const doc = await fromUuid(id);
        if (doc) {
          const sys = doc.system ?? {};
          const stats = [];
          const add = (k, v) => { if (v !== undefined && v !== null && v !== "" && v !== 0) stats.push({ k, v: String(v) }); };
          add("TYPE", sys.subtype || sys.type);
          add("PRICE", sys.price ? `${sys.price}¥` : "");
          add("AVAIL", sys.avail);
          add("ESSENCE", sys.essence);
          add("KARMA", sys.value);
          add("DAMAGE", sys.dmgDef);
          add("DRAIN", sys.drain);
          add("PAGE", sys.page ? `${sys.product ?? ""} p${sys.page}` : "");
          det = { name: doc.name, meta: doc.type,
            stats, description: sys.description || "<em>No description in the source data.</em>" };
        }
      } catch (err) { console.warn("sr6-forge | detail fetch failed", err); }
    }
    if (!det) return;
    this._detailCache.set(cacheKey, det);
    this.detail = det;
    this.#renderDetailOnly();
  }

  /** Patch just the detail pane — avoids a full re-render (and scroll jumps). */
  #renderDetailOnly() {
    const pane = this.element?.querySelector(".detail-pane");
    if (!pane || !this.detail) return;
    const d = this.detail;
    const stats = (d.stats ?? []).map((s) => `<dt>${s.k}</dt><dd>${foundry.utils.escapeHTML(s.v)}</dd>`).join("");
    pane.innerHTML = `
      <div class="dp-name">${foundry.utils.escapeHTML(d.name)}</div>
      ${d.meta ? `<div class="dp-meta">${foundry.utils.escapeHTML(d.meta)}</div>` : ""}
      ${stats ? `<dl class="dp-stats">${stats}</dl>` : ""}
      <div class="dp-desc">${d.description ?? ""}</div>`;
  }

  #onChange(ev) {
    const el = ev.target;
    const e = this.engine;
    switch (el.dataset.change) {
      case "priority": e.setPriority(el.dataset.column, el.value || null); break;
      case "ruleset": e.setRuleset(el.value); break;
      case "spec": e.spend({ kind: "spec", target: el.dataset.skill, spec: el.value || null }); break;
      case "aspected": e.setMagicPath(e.state.morId, { aspectedSkill: el.value || null }); break;
      case "lifestyle": e.spend({ kind: "lifestyle", id: el.value || null }); break;
      case "qualityFilter": this.ui.qualityFilter = el.value; break;
      case "shopSubtype": this.ui.shopSubtype = el.value; break;
      case "moduleChoice": {
        const pick = e.state.lifepath[Number(el.dataset.index)];
        if (pick) (pick.choices ??= {})[Number(el.dataset.choice)] = el.value || null;
        break;
      }
      case "qualityNote": {
        const q = e.state.qualities.find((x) => x.genesisID === el.dataset.genesisId);
        if (q) q.note = el.value;
        return;                                   // no re-render while typing
      }
      case "name": e.state.name = el.value; return;
      case "contactField": {
        const i = Number(el.dataset.index);
        const f = el.dataset.field;
        const text = f === "name" || f === "archetype";
        e.spend({ kind: "contact", index: i, patch: { [f]: text ? el.value : Number(el.value) } });
        if (text) { this.#autosave(); return; }    // typing must not re-render
        break;
      }
      default: return;
    }
    this.render();
  }

  /* =============================== actions ================================ */
  #go(dir) {
    const i = STEPS.indexOf(this.step);
    this.step = STEPS[Math.min(STEPS.length - 1, Math.max(0, i + dir))];
    this._scroll.body = 0;
    this.#autosave();
    this.render();
  }
  static #onNext() { this.#go(+1); }
  static #onBack() { this.#go(-1); }
  static #onGoto(_ev, target) {
    this.step = target.dataset.step;
    this._scroll.body = 0;
    this.render();
  }
  static #onToggleIssues() { this.ui.issuesOpen = !this.ui.issuesOpen; this.render(); }

  async #autosave() {
    await DraftStore.save(this.draftId, {
      name: this.engine.state.name, step: this.step, engineState: this.engine.toDraft(),
    });
  }
  static async #onSaveDraft() {
    await this.#autosave();
    ui.notifications.info(`SR6 Forge: draft saved${this.engine.state.name ? ` — ${this.engine.state.name}` : ""}.`);
  }

  static #onPickMethod(_ev, t) { this.engine.setMethod(t.dataset.method); this.render(); }
  static #onPickMetatype(_ev, t) { this.engine.setMetatype(t.dataset.metatype); this.render(); }
  static #onPickMor(_ev, t) {
    this.engine.setMagicPath(t.dataset.mor, { aspectedSkill: this.engine.state.aspectedSkill });
    this.render();
  }

  #spend(op, keepFilter) {
    const res = this.engine.spend(op);
    if (!res.ok) ui.notifications.warn(`SR6 Forge: ${res.reason.replaceAll("-", " ")}`);
    if (keepFilter) this._focusFilter = keepFilter;
    this.render();
  }

  static #onAdjust(_ev, t) {
    const d = t.dataset;
    const op = { kind: d.kind, target: d.target, delta: Number(d.delta ?? 1) };
    if (d.pool) op.pool = d.pool;
    this.#spend(op, d.kind === "skill" ? "skill" : null);
  }
  static #onAddQuality(_ev, t) {
    const d = t.dataset;
    // category/karma come from the pack row: chargen-data's qualityMeta only
    // covers the books we parsed, so it cannot be the sole source of truth.
    this.#spend({ kind: "quality", genesisID: d.genesisId, name: d.name,
      positive: d.category !== "negative", karma: Math.abs(Number(d.value ?? 0)) }, "quality");
  }
  static #onRemoveQuality(_ev, t) {
    this.#spend({ kind: "quality", genesisID: t.dataset.genesisId, remove: true });
  }
  static #onAddPurchase(_ev, t) {
    const d = t.dataset;
    this.#spend({ kind: "purchase", uuid: d.uuid, name: d.name, price: Number(d.price ?? 0),
      avail: Number(d.avail ?? 0), essence: Number(d.essence ?? 0),
      itemType: d.itemType, stack: true }, "shop");
  }
  static #onRemovePurchase(_ev, t) { this.#spend({ kind: "purchase", uuid: t.dataset.uuid, remove: true }); }
  static #onAddPick(_ev, t) {
    const d = t.dataset;
    this.#spend({ kind: d.kind, uuid: d.uuid, name: d.name, cost: Number(d.cost ?? 0) }, "shop");
  }
  static #onRemovePick(_ev, t) {
    this.#spend({ kind: t.dataset.kind, uuid: t.dataset.uuid, remove: true });
  }
  static #onAddModule(_ev, t) {
    this.#spend({ kind: "lifemodule", id: t.dataset.id, stage: t.dataset.stage });
  }
  static #onRemoveModule(_ev, t) {
    this.#spend({ kind: "lifemodule", id: t.dataset.id, remove: true });
  }
  static #onAddContact() { this.#spend({ kind: "contact", name: "" }); }
  static #onRemoveContact(_ev, t) { this.#spend({ kind: "contact", index: Number(t.dataset.index), remove: true }); }
  static #onAddKnowledge() {
    const root = this.element;
    const name = root.querySelector("[name=knowledge-name]")?.value?.trim();
    if (!name) return ui.notifications.warn("SR6 Forge: enter a name first.");
    this.#spend({ kind: "knowledge", name,
      type: root.querySelector("[name=knowledge-type]")?.value ?? "knowledge",
      native: !!root.querySelector("[name=knowledge-native]")?.checked });
  }
  static #onRemoveKnowledge(_ev, t) { this.#spend({ kind: "knowledge", index: Number(t.dataset.index), remove: true }); }
  static #onAddSin(_ev, t) { this.#spend({ kind: "sin", rating: Number(t.dataset.rating ?? 1) }); }
  static #onRemoveSin(_ev, t) { this.#spend({ kind: "sin", index: Number(t.dataset.index), remove: true }); }
  static #onShopTab(_ev, t) {
    this.ui.shopTab = t.dataset.tab;
    this.ui.shopSubtype = "";
    this._scroll.body = 0;
    this.render();
  }

  static async #onFinalize() {
    if (this.engine.validate().some((i) => i.severity === "error")) {
      return ui.notifications.error("SR6 Forge: resolve all errors before creating the character.");
    }
    try {
      const actor = await commitCharacter(this.engine.commitPlan());
      await DraftStore.delete(this.draftId);
      ui.notifications.info(`SR6 Forge: ${actor.name} created.`);
      await this.close();
      actor.sheet?.render(true);
    } catch (err) {
      ui.notifications.error(`SR6 Forge: creation failed — ${err.message}`);
    }
  }
}
