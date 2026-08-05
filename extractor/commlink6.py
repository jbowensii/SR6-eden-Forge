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


def _i18n(z: zipfile.ZipFile, book: str) -> dict:
    """id -> {name, page, desc, wifi} from the English properties."""
    path = f"de/rpgframework/shadowrun6/data/{book}/i18n/{book}.properties"
    out: dict = {}
    names = set(z.namelist())
    if path not in names:
        return out
    for ln in z.read(path).decode("utf-8", "replace").splitlines():
        m = _SUBKEY.match(ln)
        if m:
            out.setdefault(m.group(1), {})[m.group(2)] = m.group(3).strip()
            continue
        m = _NAMEKEY.match(ln)
        if m:
            out.setdefault(m.group(1), {}).setdefault("name", m.group(2).strip())
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
            for child in el:
                if child.tag in ("modifications", "choices"):
                    continue
                for k, v in child.attrib.items():
                    stats[f"{child.tag}.{k}"] = v
            out[iid] = {"category": category, "tag": el.tag,
                        "attrs": dict(el.attrib), "stats": stats}
    return out


def read_book(book: str, jar: Path = DEFAULT_JAR) -> dict:
    """id -> merged record {id, name, page, desc, wifi, category, tag, type,
    subtype, price, avail, stats{}} for one Commlink6 book. {} if absent."""
    if not jar.exists():
        return {}
    with zipfile.ZipFile(jar) as z:
        text = _i18n(z, book)
        stats = _stats(z, book)
    lower = {k.lower(): v for k, v in text.items()}
    recs = {}
    for iid, s in stats.items():
        t = text.get(iid) or lower.get(iid.lower()) or {}   # ids can differ in case (mrJohnson)
        a = s["attrs"]
        recs[iid] = {
            "id": iid, "name": t.get("name", ""), "page": t.get("page", ""),
            "desc": t.get("desc", ""), "wifi": t.get("wifi", ""),
            "category": s["category"], "tag": s["tag"],
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
