"""Recover the real names of the no-subtype ELECTRONICS rows whose names got
mangled to prose fragments ("Head and", "Coding", "Be Defeated"). Each row still
carries its real price + availability, so we anchor on the KNOWN price: open the
source book at meta.page, group words into visual rows, find the row whose text
contains the item's price token, and take that row's leading alpha words as the
recovered name.

SAFETY: never touches items you have manually corrected
(data/_corrections/gear/<id>.json). Dry run by default; --apply to write. Run
tools/apply_corrections.py afterwards as the final overlay."""
import sys
import glob
import json
import os
import re
from pathlib import Path as _P

sys.path.insert(0, ".")
import pdfplumber
from extractor.ingest import load_registry
from tools.domain_lib import DATA as _DL

ELEC = _P("data/corebook/gear/electronics.json")
if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    CORR = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/_corrections/gear/*.json")}
    APPLY = "--apply" in sys.argv
    reg = load_registry(_DL)

    # a name is "mangled" if it looks like a prose fragment: starts lowercase-ish,
    # or is a stop-word phrase, or is too short/gappy to be a product name.
    _STOPWORDS = re.compile(
        r"^(head and|one|difficult|core|additional|gonzo|internal|an interval|coding|"
        r"wooden|silver|crushing|regular|hardened|bladed|be defeated|can also tell|"
        r"omones a|but is|for lengths|fighting|laser|benefiting|legs,|vectored thrust|"
        r"electronic skin coatings)\b", re.I)


    def price_tokens(system):
        raw = str(system.get("price") or "").strip()
        if not raw:
            return []
        n = re.sub(r"[^\d]", "", raw)
        out = []
        if n:
            out.append(n)                                   # 11500
            out.append(f"{int(n):,}")                        # 11,500
            if len(n) > 3:
                out.append(f"{int(n):,}".replace(",", "."))  # 11.500 (some books)
        return out


    def rows_on_page(page):
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        rows = {}
        for w in words:
            key = round(w["top"] / 3)                        # ~3pt bucket = one visual line
            rows.setdefault(key, []).append(w)
        lines = []
        for _, ws in sorted(rows.items()):
            ws.sort(key=lambda w: w["x0"])
            lines.append(ws)
        return lines


    def recover(item):
        toks = price_tokens(item["system"])
        if not toks:
            return None
        r = reg.get(item["meta"].get("book"))
        if not (r and r.get("pdf")):
            return None
        pg = item["meta"].get("page")
        try:
            with pdfplumber.open(r["pdf"]) as pdf:
                page = pdf.pages[pg - 1]
                for line in rows_on_page(page):
                    text = " ".join(w["text"] for w in line)
                    if not any(t in text.replace(" ", "") or t in text for t in toks):
                        continue
                    # leading words up to the first numeric/stat token = the name
                    lead = []
                    for w in line:
                        t = w["text"]
                        if re.match(r"^[\dÂ¥¥]", t) or re.match(r"^[-—/]$", t):
                            break
                        lead.append(t)
                    name = " ".join(lead).strip(" -—:")
                    # sanity: a real name has >=2 alpha chars and isn't itself a stat
                    if len(re.sub(r"[^A-Za-z]", "", name)) >= 3 and not re.match(r"^\d", name):
                        return name[:60]
        except Exception as e:
            return None
        return None


    elec = json.load(open(ELEC, encoding="utf-8"))
    changed = []
    skipped_corr = 0
    for it in elec["items"]:
        if it["system"].get("subtype"):
            continue
        if it["id"] in CORR:
            skipped_corr += 1
            continue
        new = recover(it)
        if new and new.lower() != it["name"].lower():
            changed.append((it["name"], new, it["meta"].get("book"), it["meta"].get("page")))
            if APPLY:
                it["name"] = new

    print(f"{'APPLY' if APPLY else 'DRY RUN'} — price-anchored name recovery")
    print(f"skipped (manually corrected): {skipped_corr}")
    print(f"recovered {len(changed)} name(s):\n")
    for old, new, b, p in changed:
        print(f"    [{b} p{p}]  {old!r:32} -> {new!r}")

    if APPLY and changed:
        ELEC.write_text(json.dumps(elec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\nwritten.")
    elif not APPLY:
        print("\n(dry run — re-run with --apply to write)")
