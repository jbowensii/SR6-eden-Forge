from __future__ import annotations

import re
from collections import defaultdict

from validator.model import DataFile, Issue

DAMAGE_RE = re.compile(r"^\d{1,2}[PS](\([a-z]+\))?( \+ special)?$")
# dual-mode weapons: '3P/S', '4S/4P', '5P/5S'
DAMAGE_DUAL_RE = re.compile(r"^\d{1,2}[PS]/\d{0,2}[PS]$")
DAMAGE_FORMULA_RE = re.compile(r"^\(?(Rating|Force)\b[^A-Z]*[PS]\)?$")
MAX_AVAIL = 30
MAX_PRICE = 10_000_000
MAX_PAGE = 1500


def _issue(df: DataFile, item: dict | None, rule: str, message: str) -> Issue:
    return Issue(
        file=str(df.path),
        item_id=item.get("id") if item else None,
        rule=rule,
        message=message,
    )


def _check_duplicates(files: list[DataFile]) -> list[Issue]:
    seen: dict[tuple[str, str], list[tuple[DataFile, dict]]] = defaultdict(list)
    for df in files:
        for item in df.payload.get("items", []):
            seen[(df.book, item.get("id", ""))].append((df, item))
    issues = []
    for (book, item_id), hits in seen.items():
        if len(hits) > 1:
            locations = ", ".join(str(df.path) for df, _ in hits)
            for df, item in hits[1:]:
                issues.append(
                    _issue(df, item, "duplicate-id", f"id {item_id!r} duplicated in book {book!r}: {locations}")
                )
    return issues


def _check_item(df: DataFile, item: dict) -> list[Issue]:
    issues = []
    system = item.get("system", {})
    meta = item.get("meta", {})

    dmg_def = system.get("dmgDef", "")
    is_formula = bool(DAMAGE_FORMULA_RE.match(dmg_def))  # e.g. "(Rating/2)P", "Force x 1P"
    is_special = dmg_def in ("Special", "Grenade", "Missile")
    is_valid = DAMAGE_RE.match(dmg_def) or DAMAGE_DUAL_RE.match(dmg_def)
    if dmg_def and not is_special and not is_formula and not is_valid:
        issues.append(_issue(df, item, "damage-format", f"bad damage code {dmg_def!r}"))

    if str(system.get("type", "")).startswith("WEAPON_"):
        if not system.get("skill"):
            issues.append(_issue(df, item, "weapon-fields", "weapon has no skill"))
        if not system.get("dmgDef"):
            issues.append(_issue(df, item, "weapon-fields", "weapon has no dmgDef"))

    if system.get("avail", 0) > MAX_AVAIL:
        issues.append(_issue(df, item, "plausibility", f"avail {system['avail']} > {MAX_AVAIL}"))
    if system.get("price", 0) > MAX_PRICE:
        issues.append(_issue(df, item, "plausibility", f"price {system['price']} > {MAX_PRICE}"))
    if meta.get("page", 1) > MAX_PAGE:
        issues.append(_issue(df, item, "plausibility", f"page {meta['page']} > {MAX_PAGE}"))
    return issues


def _check_path(df: DataFile) -> list[Issue]:
    parts = df.path.parts
    if len(parts) < 3:
        return []  # path too short to follow <book>/<domain>/<category>.json convention
    book_part, domain_part, file_part = parts[-3], parts[-2], parts[-1]
    expected = (df.book, df.domain, f"{df.category}.json")
    if (book_part, domain_part, file_part) != expected:
        return [
            _issue(
                df,
                None,
                "path-mismatch",
                f"path says {book_part}/{domain_part}/{file_part}, envelope says "
                f"{expected[0]}/{expected[1]}/{expected[2]}",
            )
        ]
    return []


def check_gear(files: list[DataFile]) -> list[Issue]:
    issues = _check_duplicates(files)
    for df in files:
        issues.extend(_check_path(df))
        for item in df.payload.get("items", []):
            issues.extend(_check_item(df, item))
    return issues
