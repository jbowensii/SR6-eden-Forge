"""Phase 2 of description recovery: fill still-empty CRITTER descriptions from
the public Shadowrun Wiki (Fandom) for named creatures whose flavor text is not
in the local books (mundane/awakened animals, etc.). Uses the bot-friendly
MediaWiki parse API (the HTML pages 402 the plain fetcher and the extracts API is
disabled), pulls the lead prose paragraph(s), strips wiki markup, and stores the
result locally in the user's own module (personal use — the user owns the books).

Only fills items whose description is empty; never overwrites. Skips manually
corrected items. Dry run by default (reports found/miss, no content printed);
--apply writes. Rate-limited. Optional --limit N. Run apply_corrections.py after."""
import sys
import glob
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path as _P

APPLY = "--apply" in sys.argv
DOMAIN = "critters"
LIMIT = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), None)
CORR = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/_corrections/*/*.json")}
API = "https://shadowrun.fandom.com/api.php"
UA = "Mozilla/5.0 (SR6-eden-Forge personal-module description fetch)"
MIN_LEN = 60
MAX_LEN = 1200


def _name_variants(name):
    # try the item name and cleaned forms (drop parentheticals / slash alternates)
    base = re.sub(r"\s*\(.*?\)\s*", " ", name).strip()
    variants = [name, base]
    if "/" in base:
        variants += [p.strip() for p in base.split("/")]
    seen, out = set(), []
    for v in variants:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def _fetch_wikitext(title):
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "redirects": "1"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    if "error" in data:
        return None
    return data.get("parse", {}).get("wikitext", {}).get("*")


def _strip(wt):
    wt = re.sub(r"\{\{[^{}]*\}\}", "", wt)          # templates (may need 2 passes)
    wt = re.sub(r"\{\{[^{}]*\}\}", "", wt)
    wt = re.sub(r"<ref[^>]*>.*?</ref>", "", wt, flags=re.S)
    wt = re.sub(r"<ref[^>]*/>", "", wt)
    wt = re.sub(r"<[^>]+>", "", wt)                  # stray html
    wt = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", wt)  # [[link|text]] -> text
    wt = re.sub(r"'''?", "", wt)                     # bold/italic
    wt = re.sub(r"__[A-Z]+__", "", wt)               # magic words
    return wt


def _lead_prose(wt):
    for raw in _strip(wt).splitlines():
        ln = raw.strip()
        if len(ln) < MIN_LEN:
            continue
        if ln[0] in "{|!=[*#:;":       # tables, lists, headers, files
            continue
        if ln.lower().startswith(("file:", "image:", "category:", "redirect")):
            continue
        return re.sub(r"\s+", " ", ln)[:MAX_LEN]
    return None


def fetch_description(name):
    for title in _name_variants(name):
        try:
            wt = _fetch_wikitext(title)
        except Exception:
            wt = None
        if not wt:
            continue
        prose = _lead_prose(wt)
        if prose:
            return prose, title
    return None, None


def main():
    files = sorted(glob.glob(f"data/corebook/{DOMAIN}/*.json"))
    targets = []
    for f in files:
        payload = json.load(open(f, encoding="utf-8"))
        for it in payload.get("items", []):
            if it["id"] in CORR:
                continue
            if not (it["system"].get("description") or "").strip():
                targets.append((f, payload, it))
    if LIMIT:
        targets = targets[:LIMIT]

    found = miss = 0
    dirty = {}
    for i, (f, payload, it) in enumerate(targets):
        prose, title = fetch_description(it["name"])
        if prose:
            found += 1
            it["system"]["description"] = prose
            dirty[f] = payload
            print(f"  ✓ {it['name'][:28]:28} <- {title}", flush=True)
        else:
            miss += 1
            print(f"  · {it['name'][:28]:28} (no page)", flush=True)
        time.sleep(1.0)   # be polite to the wiki

    if APPLY:
        for f, payload in dirty.items():
            _P(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n{'APPLY' if APPLY else 'DRY RUN'} — wiki fill ({DOMAIN})")
    print(f"  found: {found}   no page: {miss}   of {len(targets)} empty")
    if not APPLY:
        print("(dry run — re-run with --apply, then tools/apply_corrections.py)")


if __name__ == "__main__":
    main()
