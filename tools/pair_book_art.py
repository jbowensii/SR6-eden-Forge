"""Pair an extracted book illustration to the catalogue item it actually depicts.

``tools/name_book_art.py`` pairs on page number alone — a graphic is claimed when
its (book, page) holds exactly one item still wanting art. That is cheap and it
is wrong more often than it looks: it matched printed page numbers against
PHYSICAL page indexes (they differ by ``pageOffset``), so on Double Clutch page
22 it handed the Harley-Davidson Centaur's picture to the Evo-Echo Stiletto, and
in Astral Ways it named a picture of a burning metaplane "silap" after the
critter whose stat block happened to sit under it. 44 pairings, several of them
confidently wrong. A wrong picture is worse than no picture.

This tool reads the page instead of counting it. Two signals, both measured
against hand-checked pairings before being trusted:

**Overlay caption.** Shadowrun's art is labelled. A vehicle plate in Double
Clutch, a product name stamped across a Krime Katalog page, an archetype name
burned into a Berlin portrait — the label is a text line drawn ON the artwork,
inside the image's own rectangle. When a line that sits wholly inside the
rectangle *is* an item's name (allowing a short qualifier: "Terracotta ferrus
major", "GTI Anubis Stealth Grav-Ship"), that is the artist naming the subject.
Measured precision on a hand-checked sample: 25/25.

**Adjacent heading.** Where there is no overlay label, the entry's heading may
sit against the art — under it, or in the neighbouring column. That is weaker,
because a heading under a picture belongs to the picture in Krime Katalog and to
the NEXT entry in Berlin's vehicle pages. It is scored, not trusted: distance
and side, how much bigger than body text the line is, whether the item's cited
page agrees, whether the image carries an alpha mask (cut-out object art does;
a flat rectangle is usually a background), and whether anything else on the page
competes for it. Above 80 the hand-checked precision was 26/27; the band just
below it fell to roughly half, so 80 is where the line is drawn.

Two shapes are refused outright. An image whose rectangle spans the full page
width but only part of its height is a section banner — the heading beneath it
starts the next entry, it does not name the picture. A thin full-width strip is
page furniture. Both produced false pairings in testing.

Everything else stays unpaired, and most of it should: 915 of the 1,867
extracted graphics come from two books that have no catalogue items at all, and
a book page carries far more art than it carries items.

    python tools/pair_book_art.py --dry-run
    python tools/pair_book_art.py --report        # every candidate + evidence
    python tools/pair_book_art.py --audit         # check pairings already made
    python tools/pair_book_art.py
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                          # noqa: E402

try:                                                            # noqa: SIM105
    from extractor.quiet import quiet_pdf_noise
    quiet_pdf_noise()
except Exception:                                               # noqa: BLE001
    pass

import fitz                                                     # noqa: E402

NOT_BOOKS = {"generic", "iconsets"}
#: "p254_x4595" — the page and PDF object id the extractor stamps on every file.
TAG = re.compile(r"(?:^|_)p(\d{2,4})_x(\d+)$")
#: table-of-contents leaders, and the "SECTION // CHAPTER" running head
_TOC = re.compile(r"\.{4,}")
_RUNHEAD = "//"

#: how far an item's cited (printed) page may sit from the physical page it is
#: paired on. Offsets are 0 or 1 across the library and a stat block can run
#: over a page, so 2 covers it without letting a cross-reference in.
PAGE_TOL = 2
#: a caption may carry a short qualifier around the name ("Terracotta ferrus
#: major"); more than this and the line is prose that mentions the item.
QUALIFIER = 20
#: minimum characters in a name before it is distinctive enough to match on
MIN_NAME = 6

CAPTION_SCORE = 95.0
DEFAULT_MIN_SCORE = 80.0


def norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.casefold())).strip()


def slug(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (name or "").casefold())).strip("_")


# ---------------------------------------------------------------- library ---

def load_items(data: _P) -> list[dict]:
    out = []
    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for path in book.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:                                   # noqa: BLE001
                continue
            if not isinstance(payload, dict):
                continue
            for it in payload.get("items", []) or []:
                meta = it.get("meta") or {}
                if not meta.get("book") or meta.get("page") is None:
                    continue
                out.append(dict(path=path, book=meta["book"], page=int(meta["page"]),
                                name=it.get("name") or "", img=it.get("img"),
                                id=it.get("id"),
                                type=((it.get("system") or {}).get("type"))))
    return out


def load_images(assets: _P) -> list[dict]:
    out = []
    if not assets.is_dir():
        return out
    for book in sorted(d for d in assets.iterdir() if d.is_dir() and d.name not in NOT_BOOKS):
        for p in sorted(book.glob("*")):
            if not p.is_file():
                continue
            m = TAG.search(p.stem)
            if m:
                out.append(dict(book=book.name, page=int(m.group(1)), xref=int(m.group(2)),
                                path=p))
    return out


# ------------------------------------------------------------------ pages ---

def page_lines(page) -> list[dict]:
    """Every text line with its box, dominant font size and direction."""
    out = []
    for blk in page.get_text("dict").get("blocks", []):
        if blk.get("type") != 0:
            continue
        for ln in blk.get("lines", []):
            spans = ln.get("spans", [])
            txt = "".join(s.get("text", "") for s in spans)
            if not txt.strip():
                continue
            bb = ln.get("bbox")
            out.append(dict(t=txt.strip(), n=norm(txt), x0=bb[0], y0=bb[1], x1=bb[2], y1=bb[3],
                            size=round(max((s.get("size", 0) for s in spans), default=0), 1),
                            dir=ln.get("dir", (1, 0))))
    return out


def relation(rect, l) -> tuple[str, float]:
    """Where a text line sits relative to an image rectangle."""
    x0, y0, x1, y1 = rect
    cx, cy = (l["x0"] + l["x1"]) / 2, (l["y0"] + l["y1"]) / 2
    ov = min(x1, l["x1"]) - max(x0, l["x0"])
    w = max(1.0, min(x1 - x0, l["x1"] - l["x0"]))
    if x0 - 2 <= cx <= x1 + 2 and y0 - 2 <= cy <= y1 + 2:
        return "IN", 0.0
    if ov / w > 0.2 and l["y0"] >= y1 - 2:
        return "BELOW", l["y0"] - y1
    if ov / w > 0.2 and l["y1"] <= y0 + 2:
        return "ABOVE", y0 - l["y1"]
    return "SIDE", min(abs(l["x0"] - x1), abs(x0 - l["x1"]))


def geo_score(rel: str, gap: float) -> float:
    if rel == "IN":
        return 60.0
    if rel == "BELOW":
        return max(-25.0, 60 - gap * 0.30)
    if rel == "SIDE":
        return max(-25.0, 40 - gap * 0.25)
    return max(-25.0, 25 - gap * 0.20)


def contained(rect, l) -> bool:
    x0, y0, x1, y1 = rect
    return (l["x0"] >= x0 - 2 and l["x1"] <= x1 + 2
            and l["y0"] >= y0 - 2 and l["y1"] <= y1 + 2)


def caption_names(line_n: str, names: dict) -> list[str]:
    """Item names this line is a caption FOR (name +/- a short qualifier)."""
    hits = []
    for n in names:
        if line_n == n:
            hits.append(n)
        elif (line_n.startswith(n + " ") or line_n.endswith(" " + n)) \
                and len(line_n) - len(n) <= QUALIFIER:
            hits.append(n)
    return hits


# ------------------------------------------------------------------ scan ----

def scan(data: _P, items: list[dict], images: list[dict],
         only: set[str] | None = None) -> list[dict]:
    """One pass over every PDF that has both art and items; returns candidates."""
    books = json.loads((data / "books.json").read_text(encoding="utf-8"))
    names: dict[str, dict[str, list[dict]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for it in items:
        n = norm(it["name"])
        if len(n) >= MIN_NAME:
            names[it["book"]][n].append(it)
    by_book = collections.defaultdict(lambda: collections.defaultdict(list))
    for im in images:
        by_book[im["book"]][im["page"]].append(im)

    rows: list[dict] = []
    for book in sorted(by_book):
        if only and book not in only:
            continue
        if not names.get(book):
            continue
        pdf = (books.get(book) or {}).get("pdf")
        if not pdf or not _P(pdf).is_file():
            print(f"  {book:24} no readable PDF — skipped", file=sys.stderr)
            continue
        nm = names[book]
        doc = fitz.open(pdf)
        for phys, ims in sorted(by_book[book].items()):
            if phys - 1 >= doc.page_count:
                continue
            page = doc[phys - 1]
            W, H = page.rect.width, page.rect.height
            lines = page_lines(page)
            sizes = collections.Counter(round(l["size"]) for l in lines)
            body = sizes.most_common(1)[0][0] if sizes else 0
            objs = {i[0]: i for i in page.get_images(full=True)}
            for im in ims:
                try:
                    rects = page.get_image_rects(im["xref"])
                except Exception:                               # noqa: BLE001
                    rects = []
                if not rects:
                    continue
                rect = max(([r.x0, r.y0, r.x1, r.y1] for r in rects),
                           key=lambda q: (q[2] - q[0]) * (q[3] - q[1]))
                fw = (rect[2] - rect[0]) / W
                fh = (rect[3] - rect[1]) / H
                area = fw * fh
                # a full-width band that is not also full-height is section
                # decoration; the heading under it starts the next entry
                banner = fw >= 0.95 and fh <= 0.80
                strip = fw >= 0.95 and fh <= 0.30
                info = objs.get(im["xref"])
                alpha = bool(info[1]) if info else False

                best: dict[str, tuple] = {}
                for l in lines:
                    if abs(l["dir"][0]) < 0.9:                  # rotated spine text
                        continue
                    # --- overlay caption -------------------------------------
                    if (not strip and area <= 0.85 and contained(rect, l)
                            and not _TOC.search(l["t"]) and _RUNHEAD not in l["t"]):
                        for n in caption_names(l["n"], nm):
                            for it in nm[n]:
                                if abs(it["page"] - phys) > PAGE_TOL:
                                    continue
                                ev = dict(kind="caption", rel="IN", gap=0.0, size=l["size"],
                                          body=body, dp=abs(it["page"] - phys), text=l["t"],
                                          fw=round(fw, 2), fh=round(fh, 2), alpha=alpha,
                                          banner=banner, score=CAPTION_SCORE)
                                cur = best.get(it["id"])
                                if cur is None or CAPTION_SCORE > cur[1]["score"]:
                                    best[it["id"]] = (it, ev)
                    # --- adjacent heading ------------------------------------
                    if l["size"] < 11.0 or l["size"] - body < 1.5:
                        continue
                    if l["n"] not in nm:
                        continue
                    rel, gap = relation(rect, l)
                    for it in nm[l["n"]]:
                        dp = abs(it["page"] - phys)
                        if dp > PAGE_TOL:
                            continue
                        s = geo_score(rel, gap)
                        s += max(0.0, min(18.0, (l["size"] - body) * 2.0))
                        s += 14 if dp == 0 else 10 if dp == 1 else 2
                        s += 12 if alpha else -18
                        if area > 0.85:
                            s -= 40
                        if banner:
                            s -= 45
                        ev = dict(kind="heading", rel=rel, gap=round(gap, 1), size=l["size"],
                                  body=body, dp=dp, text=l["t"], fw=round(fw, 2),
                                  fh=round(fh, 2), alpha=alpha, banner=banner, score=round(s, 1))
                        cur = best.get(it["id"])
                        if cur is None or s > cur[1]["score"]:
                            best[it["id"]] = (it, ev)
                for it, ev in best.values():
                    rows.append(dict(book=book, phys=phys, xref=im["xref"], path=im["path"],
                                     item=it, ev=ev))
        doc.close()
        print(f"  {book:24} scanned", file=sys.stderr)
    return rows


def resolve(rows: list[dict]) -> list[dict]:
    """Penalise ambiguity, then let one image win each item."""
    by_img = collections.defaultdict(list)
    for r in rows:
        by_img[(r["book"], r["phys"], r["xref"])].append(r)
    kept: list[dict] = []
    for v in by_img.values():
        # A label drawn ON the picture settles what the picture shows. Where
        # there is one, the headings lying around the page are not rivals — in
        # Berlin's vehicle spread and on Deadly Arts p. 63 the neighbouring
        # heading belongs to the NEXT entry every time, and letting it vote
        # dragged six verified-correct captions below the threshold.
        caps = [r for r in v if r["ev"]["kind"] == "caption"]
        v = caps or v
        # Every other name in reach is a rival, however much worse its geometry
        # looks. Letting only the close ones count admitted the core rulebook's
        # weapon spreads, where one small picture sits among five headings and
        # the label is printed ABOVE the art — the best-scoring heading there is
        # the next gun down the column, and it was wrong every time.
        # Two items with the SAME name are duplicate records, not ambiguity.
        distinct = len({norm(r["item"]["name"]) for r in v})
        for r in v:
            r["rivals"] = distinct
            r["score"] = r["ev"]["score"] - 22 * (distinct - 1)
        kept.extend(v)
    rows = kept
    by_item = collections.defaultdict(list)
    for r in rows:
        by_item[(r["book"], r["item"]["id"])].append(r)
    for v in by_item.values():
        v.sort(key=lambda r: -r["score"])
        for r in v[1:]:
            r["score"] -= 20
    rows.sort(key=lambda r: -r["score"])
    return rows


# ------------------------------------------------------------------ apply ---

def destination(src: _P, item: dict) -> _P:
    s = slug(item["name"])
    if not s or src.stem.startswith(s + "_"):
        return src
    m = TAG.search(src.stem)
    tag = f"p{m.group(1)}_x{m.group(2)}" if m else src.stem
    return src.with_name(f"{s}_{tag}{src.suffix}")


def clear_img(items: list[dict], targets: set[str], dry: bool) -> int:
    """Set ``img`` to null on every item pointing at one of these paths."""
    cleared = 0
    for path in {it["path"] for it in items if (it.get("img") or "") in targets}:
        payload = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for entry in payload.get("items", []) or []:
            if (entry.get("img") or "") in targets:
                entry["img"] = None
                cleared += 1
                dirty = True
        if dirty and not dry:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    return cleared


def unpair(data: _P, assets: _P, items: list[dict], targets: set[str], dry: bool) -> int:
    """Undo named pairings: clear the items and give the files their page name."""
    targets = {t.replace("\\", "/") for t in targets}
    holders = [it for it in items if (it.get("img") or "") in targets]
    for it in holders:
        print(f"  clearing [{it['type']}] {it['name']}  ({it['img']})")
    missing = targets - {it.get("img") for it in holders}
    for m in sorted(missing):
        print(f"  {m}: no item points at it")
    cleared = clear_img(items, targets, dry)
    renamed = 0
    for rel in sorted(targets):
        src = assets / rel
        m = TAG.search(src.stem)
        if not src.is_file() or not m:
            continue
        plain = src.with_name(f"p{m.group(1)}_x{m.group(2)}{src.suffix}")
        if plain != src and not plain.exists():
            if not dry:
                src.rename(plain)
            renamed += 1
    print(f"{'would clear' if dry else 'cleared'} {cleared} item(s); "
          f"{'would un-name' if dry else 'un-named'} {renamed} file(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--book", action="append", default=None,
                    help="limit to these book slugs (repeatable)")
    ap.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true",
                    help="print every candidate with its evidence and stop")
    ap.add_argument("--audit", action="store_true",
                    help="list existing book-art pairings this model does not support")
    ap.add_argument("--unpair", action="append", default=None, metavar="BOOK/FILE.png",
                    help="clear one pairing and give the file its page name back "
                         "(repeatable). Unsupported is not the same as wrong — the "
                         "model cannot confirm a one-word name or a portrait with no "
                         "caption, so --audit reports and this removes, by hand.")
    args = ap.parse_args()

    data = args.data or data_root()
    assets = data / "_assets"
    print(f"library: {data}")

    items = load_items(data)
    images = load_images(assets)
    print(f"{len(items)} items with a book+page, {len(images)} extracted graphics")

    if args.unpair:
        return unpair(data, assets, items, set(args.unpair), args.dry_run)

    only = set(args.book) if args.book else None
    rows = resolve(scan(data, items, images, only))

    if args.report:
        for r in rows:
            e = r["ev"]
            print(f"{r['score']:>6.1f} {e['kind']:7} {r['book']:20} p{r['phys']:<4} "
                  f"x{r['xref']:<6} {e['rel']:5} gap={e['gap']:>6} sz={e['size']:>5}/{e['body']} "
                  f"dp={e['dp']} fw={e['fw']} fh={e['fh']} a={int(e['alpha'])} "
                  f"riv={r['rivals']} | {e['text'][:38]:38} -> [{r['item']['type']}] "
                  f"{r['item']['name'][:34]}")
        for th in (95, 90, 80, 70, 60, 50):
            keep = [r for r in rows if r["score"] >= th]
            print(f"  score>={th:>3}: {len(keep):>4} pairings, "
                  f"{len({(r['book'], r['phys'], r['xref']) for r in keep}):>4} graphics, "
                  f"{len({(r['book'], r['item']['id']) for r in keep}):>4} items")
        return 0

    accepted = [r for r in rows if r["score"] >= args.min_score]
    # one graphic may legitimately serve two duplicate item records, but never
    # two different subjects
    by_img = collections.defaultdict(list)
    for r in accepted:
        by_img[(r["book"], r["phys"], r["xref"])].append(r)
    accepted = [r for v in by_img.values() if len({norm(x["item"]["name"]) for x in v}) == 1
                for r in v]

    if args.audit:
        supported = {(r["book"], r["item"]["id"]) for r in accepted}
        rel_ok = {(r["book"], r["item"]["id"]): r for r in accepted}
        bad = []
        for it in items:
            img = it.get("img") or ""
            if not img or img.startswith("generic/") or img.startswith("iconsets/"):
                continue
            key = (it["book"], it["id"])
            if key in supported:
                cur = (assets / img)
                want = rel_ok[key]["path"]
                if cur.name != want.name and cur.stem.split("_p")[-1] != want.stem.split("_p")[-1]:
                    bad.append((it, img, f"model pairs it with {want.name}"))
                continue
            bad.append((it, img, "no supporting caption or heading on the page"))
        print(f"\n{len(bad)} existing book-art pairing(s) the model cannot support:")
        for it, img, why in sorted(bad, key=lambda b: b[1]):
            print(f"  [{it['type']:>12}] {it['name'][:34]:34} -> {img}  ({why})")
        print("\nUnsupported is not proof of wrong: a one-word name, or a portrait "
              "with no printed label,\nleaves nothing to check against. Look at the "
              "picture, then remove the bad ones by name:\n"
              "    python tools/pair_book_art.py --unpair <book>/<file>.png")
        return 0

    print(f"\n{len(accepted)} pairing(s) at score >= {args.min_score} "
          f"({len({(r['book'], r['phys'], r['xref']) for r in accepted})} graphics, "
          f"{len({(r['book'], r['item']['id']) for r in accepted})} items)")
    for r in accepted:
        e = r["ev"]
        mark = "" if not (r["item"].get("img") or "").startswith(("generic/", "iconsets/")) \
            else " (replaces category icon)"
        print(f"  {r['score']:>5.1f} {e['kind']:7} {r['book']:20} {r['path'].name:32} "
              f"-> [{r['item']['type']}] {r['item']['name'][:30]}{mark}")

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    # --- rename the files after what they show -------------------------------
    renames: dict[_P, _P] = {}
    for r in accepted:
        src = r["path"]
        dest = destination(src, r["item"])
        if dest != src and not dest.exists():
            renames[src] = dest
    for src, dest in renames.items():
        src.rename(dest)

    final = {}
    for r in accepted:
        src = r["path"]
        final[(r["book"], r["item"]["id"])] = renames.get(src, src).relative_to(assets).as_posix()

    # A file renamed out from under an older, wrong pairing leaves that item
    # pointing at a path that no longer exists — the Double Clutch Stiletto held
    # the Harley-Davidson Centaur's picture, and renaming it to the Centaur
    # would have left the Stiletto pointing at nothing. Cut those loose.
    moved = {src.relative_to(assets).as_posix() for src in renames}
    keeps = set(final.values())
    orphaned = clear_img(items, {m for m in moved if m not in keeps}, dry=False)
    if orphaned:
        print(f"cleared {orphaned} item(s) left pointing at a renamed file")

    # --- point the items at their picture ------------------------------------
    assigned = 0
    for path in {r["item"]["path"] for r in accepted}:
        payload = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for entry in payload.get("items", []) or []:
            meta = entry.get("meta") or {}
            key = (meta.get("book"), entry.get("id"))
            if key in final and entry.get("img") != final[key]:
                entry["img"] = final[key]
                assigned += 1
                dirty = True
        if dirty:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    print(f"\nrenamed {len(renames)} file(s); {assigned} item(s) now show their book art")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
