"""Reader for the Commlink6 (RPGFramework de.rpgframework.shadowrun6) dataset
bundled in `commlink6-<ver>-complete.jar`. Two parallel layers per book, keyed by
a stable `id`:

  data/<book>/data/<category>.xml   — stats: type, subtype, price, avail + nested
                                       weapon/armor/etc. stat elements
  data/<book>/i18n/<book>.properties — English text: <prefix>.<id>=Name,
                                       .<id>.page, .<id>.desc, .<id>.wifi

We read English only. Records are keyed by id and indexed by normalized name for
cross-referencing against the SR6-eden-Forge dataset. Pure reader — no writes."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

_DEFAULT_DIR = Path("C:/Users/johnb/CommLink6/app/stable")   # standard Commlink6 install


def _resolve_jar() -> Path:
    """Commlink6 data jar: settings.json 'commlink6Jar' (a jar file OR the
    app/stable dir), else the default install; version-tolerant via glob."""
    import json
    p = None
    try:
        p = json.loads(Path("data/settings.json").read_text(encoding="utf-8")).get("commlink6Jar")
    except Exception:
        pass
    cand = Path(p) if p else _DEFAULT_DIR
    if cand.is_file():
        return cand
    if cand.is_dir():
        jars = sorted(cand.glob("commlink6-*-complete.jar"))
        if jars:
            return jars[-1]
    return _DEFAULT_DIR / "commlink6-1.14.0-complete.jar"


DEFAULT_JAR = _resolve_jar()

# our book slug -> Commlink6 book slug (English books only)
BOOK_ALIAS = {
    "corebook": "core",
    "corebook_seattle": "core",      # folded into core as *_seattle categories
    "corebook_berlin": "core",       # folded into core as *_berlin categories
    "emerald_city": "emerald",
    "kechibi_code": "kechibi",
    "krime_katalog": "krime",
    "shadows_new_orleans": "sif_new_orleans",
}
# Commlink6 books that are German-only content (ignore per user)
GERMAN_BOOKS = {"de_alpen", "de_berlin2080", "de_bundeswehr", "de_feuerlaeufer",
                "de_other", "de_piraten", "de_revierbericht", "de_sota2081",
                "de_sota2082", "de_sota2083", "de_westphalen"}
NON_CONTENT = {"icons", "placeholder", "other_us"}

# NOTE: some bundles pad the separator ("metatype.human = Human"), so allow
# whitespace around '=' — without it the 5 core metatypes lose their names.
_SUBKEY = re.compile(r"^[A-Za-z_]+\.([A-Za-z0-9_-]+)\.(desc|page|wifi|source)\s*=\s*(.*)$")
_NAMEKEY = re.compile(r"^[A-Za-z_]+\.([A-Za-z0-9_-]+)\s*=\s*(.*)$")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").casefold())


def decode_props(raw: bytes) -> str:
    """Commlink6 bundles are mostly UTF-8, but a few (kechibi, de_alpen) are
    Latin-1 — decoding those as UTF-8 mangles accented names ("Kuàizi").
    Try UTF-8 first, fall back to cp1252."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def _i18n(z: zipfile.ZipFile, book: str) -> dict:
    """id -> {name, page, desc, wifi} from the English properties."""
    path = f"de/rpgframework/shadowrun6/data/{book}/i18n/{book}.properties"
    out: dict = {}
    names = set(z.namelist())
    if path not in names:
        return out
    for ln in decode_props(z.read(path)).splitlines():
        m = _SUBKEY.match(ln)
        if m:
            out.setdefault(m.group(1), {})[m.group(2)] = m.group(3).strip()
            continue
        m = _NAMEKEY.match(ln)
        if m:
            out.setdefault(m.group(1), {}).setdefault("name", m.group(2).strip())
    return out


#: Every English display name in the jar, keyed by id — built once per jar.
#: See :func:`_all_english_names`.
_ALL_NAMES: dict[str, dict[str, str]] = {}


def _all_english_names(z: zipfile.ZipFile, jar_key: str) -> dict:
    """``id -> name`` across EVERY English properties file in the jar.

    A book's data XML routinely references entries whose display name lives in
    another book's properties file. The Dodge Scoot is defined in Double
    Clutch's data but named in the core rulebook's; MapMaster's drone is named
    in core_seattle's. Looking only in ``<book>.properties`` left 82 items in
    the library with an EMPTY name — they reached Foundry as blank rows and
    printed as ``[prose] qualities/`` with nothing after the slash.

    The book's own file still wins; this is only consulted when that misses, so
    a name deliberately overridden per book keeps its override.

    German files (``*_de.properties``) are excluded on purpose. Importing a
    German name for a book whose German PDF is not owned would import data the
    ownership rule says we may not have.
    """
    if jar_key in _ALL_NAMES:
        return _ALL_NAMES[jar_key]
    out: dict[str, str] = {}
    for n in z.namelist():
        if not (n.endswith(".properties") and "/i18n/" in n):
            continue
        if n.rsplit("/", 1)[-1][:-len(".properties")].endswith("_de"):
            continue
        for ln in decode_props(z.read(n)).splitlines():
            m = _NAMEKEY.match(ln)
            if m:
                out.setdefault(m.group(1), m.group(2).strip())
    _ALL_NAMES[jar_key] = out
    return out


def _stats(z: zipfile.ZipFile, book: str) -> dict:
    """id -> {category, tag, attrs{}, stats{}} from every category XML."""
    out: dict = {}
    prefix = f"de/rpgframework/shadowrun6/data/{book}/data/"
    for n in z.namelist():
        if not (n.startswith(prefix) and n.endswith(".xml")):
            continue
        category = n[len(prefix):-4]
        try:
            root = ET.fromstring(z.read(n))
        except ET.ParseError:
            continue
        for el in root:
            if el.tag is ET.Comment:
                continue
            iid = el.attrib.get("id")
            if not iid:
                continue
            # flatten first-level stat children (weapon/armor/vehicle/…) attrs
            stats = {}
            mods = []
            for child in el:
                if child.tag == "choices":
                    continue
                if child.tag == "modifications":
                    # What the item DOES: "+1 Body", "-1 to Con". Kept as plain
                    # dicts — extractor.effects turns the ones Eden can express
                    # into ActiveEffects. Skipping this is why every exported
                    # item modified nothing when equipped.
                    mods.extend({"tag": m.tag, **m.attrib} for m in child)
                    continue
                for k, v in child.attrib.items():
                    stats[f"{child.tag}.{k}"] = v
            out[iid] = {"category": category, "tag": el.tag,
                        "attrs": dict(el.attrib), "stats": stats, "mods": mods}
    return out


def read_book(book: str, jar: Path = DEFAULT_JAR) -> dict:
    """id -> merged record {id, name, page, desc, wifi, category, tag, type,
    subtype, price, avail, stats{}} for one Commlink6 book. {} if absent."""
    if not jar.exists():
        return {}
    with zipfile.ZipFile(jar) as z:
        text = _i18n(z, book)
        stats = _stats(z, book)
        everywhere = _all_english_names(z, str(jar))
    lower = {k.lower(): v for k, v in text.items()}
    recs = {}
    for iid, s in stats.items():
        t = text.get(iid) or lower.get(iid.lower()) or {}   # ids can differ in case (mrJohnson)
        # This book's own file first; the rest of the jar only as a fallback.
        name = t.get("name") or everywhere.get(iid) or everywhere.get(iid.lower(), "")
        if not name:
            # No English name anywhere in the jar. 132 such entries existed —
            # German-only ids like 'taliskraemerin' and 'adeptenausbildung',
            # absent even from the German properties. They were imported as
            # nameless rows. An item with no name is not data, and the
            # ownership rule already says German-only content stays out.
            continue
        a = s["attrs"]
        recs[iid] = {
            "id": iid, "name": name, "page": t.get("page", ""),
            "desc": t.get("desc", ""), "wifi": t.get("wifi", ""),
            "category": s["category"], "tag": s["tag"], "mods": s.get("mods") or [],
            "type": a.get("type", ""), "subtype": a.get("subtype", ""),
            "price": a.get("price", ""), "avail": a.get("avail", ""),
            "attrs": a, "stats": s["stats"],
        }
    return recs


def index_by_name(recs: dict) -> dict:
    """normalized-name -> record (name-carrying records only)."""
    out = {}
    for r in recs.values():
        if r["name"]:
            out.setdefault(norm(r["name"]), r)
    return out


def english_books(jar: Path = DEFAULT_JAR) -> set:
    """Commlink6 book slugs with content, English (excludes de_* and non-content)."""
    if not jar.exists():
        return set()
    books = set()
    with zipfile.ZipFile(jar) as z:
        for n in z.namelist():
            m = re.match(r"de/rpgframework/shadowrun6/data/([^/]+)/", n)
            if m:
                books.add(m.group(1))
    return books - GERMAN_BOOKS - NON_CONTENT
