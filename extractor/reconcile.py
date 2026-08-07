"""Reconcile two readings of the same book.

When a book is present as both a Commlink6 dataset and a PDF, most records
arrive twice. Usually the two agree, or only one has a value — those are easy.
The interesting case is when both state something and the statements differ.

Rather than silently pick a winner, the disagreement is recorded on the item as
``meta.conflicts`` and surfaced in the review app. Two independent
transcriptions of one publication is a QA asset: where they differ is exactly
where a human should look, and one of the two is usually wrong in a way neither
source can detect alone.

Precedence, when a choice must be made:

============================  ==========  =====================================
Field                         Wins        Why
============================  ==========  =====================================
type, subtype, rating,        Commlink6   Declared machine-readably; the page
essence, capacity, mounts                 states these in prose, if at all
description, prose            PDF         The book is the text
everything else               Commlink6   Already parsed and typed; the PDF
                                          fills only what the jar lacks
============================  ==========  =====================================

Rules constants — karma costs, caps, the priority table — are not handled here.
Those come from the books, cited to a page, through ``build_chargen_data``.
"""
from __future__ import annotations

#: The jar states these better than the page does.
JAR_WINS = frozenset({
    "type", "subtype", "rating", "maxRating", "essence", "capacity",
    "hooks", "mounts", "hookCapacity", "avail", "price",
})

#: The book states these better than the jar does.
PDF_WINS = frozenset({"description", "page"})

#: Never compared: bookkeeping, not content.
IGNORED = frozenset({
    "genesisID", "catalogId", "sr6forge", "img", "icon", "_notice",
})


def _blank(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def reconcile_item(jar_item: dict, pdf_item: dict) -> tuple[dict, list[str]]:
    """Merge one record's two readings.

    The Commlink6 record is the base — it is already structured and typed — and
    the PDF reading fills or overrides per the precedence table.

    :returns: ``(merged, conflicts)`` where each conflict reads
        ``"price: commlink6=725 pdf=750 -> commlink6"``.
    """
    merged = dict(jar_item)
    merged["system"] = dict(jar_item.get("system") or {})
    jar_sys = jar_item.get("system") or {}
    pdf_sys = pdf_item.get("system") or {}
    conflicts: list[str] = []

    for field in sorted(set(jar_sys) | set(pdf_sys)):
        if field in IGNORED:
            continue
        jv, pv = jar_sys.get(field), pdf_sys.get(field)

        if _blank(jv) and _blank(pv):
            continue
        if _blank(jv):                      # only the book has it
            merged["system"][field] = pv
            continue
        if _blank(pv):                      # only the jar has it
            merged["system"][field] = jv
            continue
        if jv == pv:
            merged["system"][field] = jv
            continue

        # both stated it, and they differ
        if field in PDF_WINS:
            merged["system"][field] = pv
            winner = "pdf"
        else:
            merged["system"][field] = jv
            winner = "commlink6"
        conflicts.append(f"{field}: commlink6={jv!r} pdf={pv!r} -> {winner}")

    if conflicts:
        meta = merged.setdefault("meta", dict(jar_item.get("meta") or {}))
        meta["conflicts"] = conflicts
        # a disagreement is worth a human's eye before it reaches a sheet
        if meta.get("qaStatus") == "approved":
            meta["qaStatus"] = "review"
    return merged, conflicts


def reconcile_library(jar_items: list[dict], pdf_items: list[dict],
                      key=lambda i: (i.get("name") or "").strip().lower()):
    """Reconcile two lists of the same book's records, matched by name.

    :returns: ``(items, stats)``. Records present in only one source pass
        through untouched; the stats say how the set broke down.
    """
    by_name: dict[str, dict] = {}
    for it in jar_items:
        by_name[key(it)] = it

    out: list[dict] = []
    stats = {"matched": 0, "conflicts": 0, "jarOnly": 0, "pdfOnly": 0}
    seen: set[str] = set()

    for pdf_it in pdf_items:
        k = key(pdf_it)
        jar_it = by_name.get(k)
        if jar_it is None:
            out.append(pdf_it)
            stats["pdfOnly"] += 1
            continue
        merged, conflicts = reconcile_item(jar_it, pdf_it)
        out.append(merged)
        seen.add(k)
        stats["matched"] += 1
        stats["conflicts"] += len(conflicts)

    for k, jar_it in by_name.items():
        if k not in seen:
            out.append(jar_it)
            stats["jarOnly"] += 1

    return out, stats
