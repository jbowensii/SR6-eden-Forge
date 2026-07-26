"""Match items lacking artwork against a local icon library by name/subtype
token overlap (deterministic, no AI). Chosen icons are COPIED into the
gitignored data/_assets/<book>/lib/ tree and wired to the item, so originals
stay untouched and nothing enters git."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

EXTS = {".png", ".webp", ".svg", ".jpg", ".jpeg"}
STOPWORDS = {"icon", "icons", "the", "and", "for", "with", "set", "pack", "final", "new", "copy", "png", "webp", "svg", "jpg", "jpeg"}
MIN_SCORE = 3


def tokens(text: str) -> set[str]:
    return {
        t
        for t in re.split(r"[^a-z0-9]+", text.casefold())
        if len(t) >= 3 and not t.isdigit() and t not in STOPWORDS
    }


def index_library(lib_root: Path) -> list[tuple[Path, set[str]]]:
    out = []
    for path in lib_root.rglob("*"):
        if path.suffix.lower() in EXTS and path.is_file():
            rel = path.relative_to(lib_root)
            out.append((path, tokens(" ".join(rel.parts))))
    return out


def item_tokens(item: dict) -> tuple[set[str], set[str]]:
    """(name tokens, context tokens from subtype/type)."""
    name = tokens(item["name"])
    context = tokens(str(item["system"].get("subtype", "")).replace("_", " "))
    context |= tokens(str(item["system"].get("type", "")).replace("_", " "))
    return name, context


def best_match(item: dict, library: list[tuple[Path, set[str]]], min_score: int = MIN_SCORE):
    name, context = item_tokens(item)
    best, best_score = None, min_score - 1
    for path, lib_tokens in library:
        name_hits = len(name & lib_tokens)
        if not name_hits:
            continue  # at least one name token must match
        score = name_hits * 2 + len(context & lib_tokens)
        if score > best_score or (score == best_score and best and len(str(path)) < len(str(best))):
            best, best_score = path, score
    return (best, best_score) if best else (None, 0)


def match_icons(lib_root: Path, data_root: Path, book: str, domain: str, min_score: int = MIN_SCORE) -> dict:
    domain_dir = data_root / book / domain
    lib = index_library(lib_root)
    dest_dir = data_root / "_assets" / book / "lib"
    dest_dir.mkdir(parents=True, exist_ok=True)

    matched = missing = 0
    for payload_path in sorted(domain_dir.glob("*.json")):
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        changed = False
        for item in payload.get("items", []):
            if item.get("img"):
                continue
            source, score = best_match(item, lib, min_score)
            if source is None:
                missing += 1
                continue
            dest = dest_dir / f"{item['id']}{source.suffix.lower()}"
            shutil.copyfile(source, dest)
            item["img"] = f"{book}/lib/{dest.name}"
            print(f"  {item['name']} <- {source.name} (score {score})")
            matched += 1
            changed = True
        if changed:
            payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"matched": matched, "still_missing": missing, "library": len(lib)}
