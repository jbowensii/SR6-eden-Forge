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

    p = sub.add_parser("parse", help="parse cached pages into data files")
    p.add_argument("--book", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--data", default="data")
    p.add_argument("--categories", default="", help="comma-separated filter")

    args = parser.parse_args(argv)
    if args.cmd == "dump":
        from extractor.dump import dump_book

        n = dump_book(Path(args.pdf), args.book, _pages(args.pages), Path(args.data))
        print(f"dumped {n} page(s)")
        return 0
    from extractor.run import parse_book  # Task 4

    return parse_book(
        args.book,
        args.domain,
        Path(args.data),
        [c for c in args.categories.split(",") if c],
    )


if __name__ == "__main__":
    sys.exit(main())
