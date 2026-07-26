from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _pages(spec: str) -> range:
    start, _, end = spec.partition("-")
    return range(int(start), int(end or start) + 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="extractor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dump", help="cache normalized page text from a PDF")
    d.add_argument("--pdf", required=True)
    d.add_argument("--book", required=True)
    d.add_argument("--pages", required=True, help="e.g. 245-304")
    d.add_argument("--data", default="data")
    d.add_argument("--columns", action="store_true", help="also cache column-ordered text (for enrich/images)")

    p = sub.add_parser("parse", help="parse cached pages into data files")
    p.add_argument("--book", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--data", default="data")
    p.add_argument("--categories", default="", help="comma-separated filter")

    e = sub.add_parser("enrich", help="attribute prose writeups to items (system.description)")
    e.add_argument("--book", required=True)
    e.add_argument("--domain", required=True)
    e.add_argument("--pages", required=True)
    e.add_argument("--data", default="data")
    e.add_argument("--force", action="store_true", help="overwrite existing descriptions")

    i = sub.add_parser("images", help="extract item artwork as PNGs into data/_assets")
    i.add_argument("--pdf", required=True)
    i.add_argument("--book", required=True)
    i.add_argument("--domain", required=True)
    i.add_argument("--pages", required=True)
    i.add_argument("--data", default="data")
    i.add_argument("--rembg", action="store_true", help="offline background removal for opaque assigned art")

    ic = sub.add_parser("icons", help="match items lacking art against a local icon library")
    ic.add_argument("--library", required=True)
    ic.add_argument("--book", required=True)
    ic.add_argument("--domain", required=True)
    ic.add_argument("--data", default="data")
    ic.add_argument("--min-score", type=int, default=3)

    args = parser.parse_args(argv)
    if args.cmd == "dump":
        from extractor.dump import dump_book
        from extractor.textcols import dump_columns

        n = dump_book(Path(args.pdf), args.book, _pages(args.pages), Path(args.data))
        print(f"dumped {n} page(s)")
        if args.columns:
            n = dump_columns(Path(args.pdf), args.book, _pages(args.pages), Path(args.data))
            print(f"dumped {n} column page(s)")
        return 0
    if args.cmd == "enrich":
        from extractor.enrich import enrich_descriptions

        stats = enrich_descriptions(Path(args.data), args.book, args.domain, _pages(args.pages), force=args.force)
        print(f"writeups matched: {stats['matched']} | descriptions updated: {stats['updated']} / {stats['items']} items")
        return 0
    if args.cmd == "images":
        from extractor.images_extract import extract_images

        stats = extract_images(Path(args.pdf), Path(args.data), args.book, args.domain, _pages(args.pages), rembg=args.rembg)
        print(f"images saved: {stats['saved']} | auto-assigned: {stats['assigned']} | left in _inbox: {stats['inbox']}")
        return 0
    if args.cmd == "icons":
        from extractor.icon_match import match_icons

        stats = match_icons(Path(args.library), Path(args.data), args.book, args.domain, args.min_score)
        print(f"library files: {stats['library']} | name-matched: {stats['matched']} | generic: {stats['generic']} | still without art: {stats['still_missing']}")
        return 0
    from extractor.run import parse_book

    return parse_book(
        args.book,
        args.domain,
        Path(args.data),
        [c for c in args.categories.split(",") if c],
    )


if __name__ == "__main__":
    sys.exit(main())
