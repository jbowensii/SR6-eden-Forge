from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from validator.loader import discover
from validator.model import Issue
from validator.sanity import check_gear
from validator.schema_check import check_file

SANITY_CHECKS = {"gear": check_gear}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="validator", description="Validate SR6-eden-Forge data files")
    parser.add_argument("path", help="data directory to validate (e.g. data/ or data/corebook)")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        print(f"error: {root} is not a directory")
        return 2

    files, issues = discover(root)

    schema_ok = []
    for df in files:
        file_issues = check_file(df)
        issues.extend(file_issues)
        if not file_issues:
            schema_ok.append(df)

    by_domain = defaultdict(list)
    for df in schema_ok:
        by_domain[df.domain].append(df)
    for domain, domain_files in sorted(by_domain.items()):
        checker = SANITY_CHECKS.get(domain)
        if checker:
            issues.extend(checker(domain_files))

    _report(issues)
    item_count = sum(len(df.payload.get("items", [])) for df in files)
    if issues:
        print(f"FAILED: {len(issues)} issue(s) in {len({i.file for i in issues})} file(s)")
        return 1
    print(f"OK: {len(files)} file(s), {item_count} item(s) validated")
    return 0


def _report(issues: list[Issue]) -> None:
    by_file = defaultdict(list)
    for issue in issues:
        by_file[issue.file].append(issue)
    for file, file_issues in sorted(by_file.items()):
        print(file)
        for issue in file_issues:
            where = f" [{issue.item_id}]" if issue.item_id else ""
            print(f"  {issue.rule}{where}: {issue.message}")
