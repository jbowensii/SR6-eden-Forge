# Gear Schema + Validator Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** JSON Schemas for the gear domain plus a standalone `python -m validator` CLI that schema-validates and sanity-checks every data file under a path.

**Architecture:** Two-layer validation — a schema pass (jsonschema Draft 2020-12, one schema per content domain, shared `meta` definitions in a common schema) and a sanity pass (Python rules per domain, including cross-file rules like duplicate detection). A loader discovers data files and pairs them with their domain schema; the CLI reports issues grouped by file and exits nonzero on any issue.

**Tech Stack:** Python 3.12+, `jsonschema>=4.21`, `pytest`. No AI dependencies — runnable by anyone.

## Global Constraints

- Python 3.12+; dependencies limited to `jsonschema` (runtime) and `pytest` (dev).
- JSON Schema dialect: Draft 2020-12.
- Target system pinned: `shadowrun6-eden` 3.3.x on Foundry v13. The `system` block field list comes verbatim from Eden's `template.json` gear type (incl. `genesis`, `dice-pool`, `matrix-device` template mixins).
- Gear `type` enum (23 values, from Eden `lang/en.json`): `ACCESSORY, AMMUNITION, ARMOR, ARMOR_ADDITION, BIOLOGY, BIOWARE, CHEMICALS, CYBERWARE, CODEMODS, DRONES, ELECTRONICS, GENETICS, MAGICAL, NANOWARE, SOFTWARE, SURVIVAL, TOOLS, VEHICLES, WEAPON_CLOSE_COMBAT, WEAPON_FIREARMS, WEAPON_RANGED, WEAPON_SPECIAL, IC`.
- **No copyrighted content in the repo**: all test fixtures use invented items (e.g. "Example Autopistol"); real data stays under gitignored `data/`.
- Data file envelope: `{book, domain, category, items[]}`; item: `{id, name, system{}, meta{}}`; `meta` = `{book, page, extractedAt, extractorVersion, qaStatus}` with `qaStatus ∈ extracted|reviewed|approved`.
- Every commit message ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Working directory for all commands: `C:\Users\johnb\Documents\Projects\SR6-eden-Forge`.

## File Structure

```
schemas/common.schema.json        ← $defs: meta, slug (shared by all domains)
schemas/gear.schema.json          ← gear data-file schema ($refs common)
validator/__init__.py             ← empty package marker
validator/__main__.py             ← python -m validator entry
validator/model.py                ← Issue + DataFile dataclasses
validator/loader.py               ← discover(root) -> list[DataFile]
validator/schema_check.py         ← check_file(df) -> list[Issue]
validator/sanity.py               ← check_gear(files) -> list[Issue]
validator/cli.py                  ← main(argv) -> int
tests/__init__.py                 ← empty
tests/conftest.py                 ← fixture factories (valid gear file dict)
tests/test_schema.py              ← schema pass tests
tests/test_loader.py              ← discovery tests
tests/test_sanity.py              ← sanity rule tests
tests/test_cli.py                 ← end-to-end CLI tests
requirements.txt                  ← jsonschema>=4.21
requirements-dev.txt              ← -r requirements.txt + pytest
pytest.ini                        ← testpaths = tests
```

---

### Task 1: Schemas + schema pass

**Files:**
- Create: `schemas/common.schema.json`
- Create: `schemas/gear.schema.json`
- Create: `validator/__init__.py`, `validator/model.py`, `validator/schema_check.py`
- Create: `requirements.txt`, `requirements-dev.txt`, `pytest.ini`
- Create: `tests/__init__.py`, `tests/conftest.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `validator.model.Issue` — `@dataclass(frozen=True)` with fields `file: str`, `item_id: str | None`, `rule: str`, `message: str`.
  - `validator.model.DataFile` — `@dataclass` with fields `path: Path`, `payload: dict`; properties `book`, `domain`, `category` reading from `payload` (return `""` if missing).
  - `validator.schema_check.check_file(df: DataFile) -> list[Issue]` — schema-validates `df.payload` against `schemas/<domain>.schema.json`; unknown domain → single Issue with rule `no-schema`; violations → rule `schema`.
  - `tests/conftest.py` fixture `gear_file() -> dict` returning a fully valid gear data-file dict.

- [ ] **Step 1: Environment + deps**

```bash
cd "C:\Users\johnb\Documents\Projects\SR6-eden-Forge"
python -m venv .venv
.venv\Scripts\pip install jsonschema pytest
```

Create `requirements.txt`:

```
jsonschema>=4.21
```

Create `requirements-dev.txt`:

```
-r requirements.txt
pytest>=8
```

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 2: Write the schemas**

Create `schemas/common.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:sr6forge:common",
  "title": "SR6-eden-Forge shared definitions",
  "$defs": {
    "slug": {
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9_]*$"
    },
    "meta": {
      "type": "object",
      "required": ["book", "page", "extractedAt", "extractorVersion", "qaStatus"],
      "additionalProperties": false,
      "properties": {
        "book": { "$ref": "#/$defs/slug" },
        "page": { "type": "integer", "minimum": 1 },
        "extractedAt": { "type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$" },
        "extractorVersion": { "type": "string", "minLength": 1 },
        "qaStatus": { "enum": ["extracted", "reviewed", "approved"] },
        "notes": { "type": "string" }
      }
    }
  }
}
```

Create `schemas/gear.schema.json` (system-block field list mirrors Eden `template.json` gear + mixins; `additionalProperties: false` so typos fail loudly):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:sr6forge:gear",
  "title": "SR6-eden-Forge gear data file",
  "type": "object",
  "required": ["book", "domain", "category", "items"],
  "additionalProperties": false,
  "properties": {
    "book": { "$ref": "urn:sr6forge:common#/$defs/slug" },
    "domain": { "const": "gear" },
    "category": { "$ref": "urn:sr6forge:common#/$defs/slug" },
    "items": {
      "type": "array",
      "items": { "$ref": "#/$defs/gearItem" }
    }
  },
  "$defs": {
    "gearItem": {
      "type": "object",
      "required": ["id", "name", "system", "meta"],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "urn:sr6forge:common#/$defs/slug" },
        "name": { "type": "string", "minLength": 1 },
        "system": { "$ref": "#/$defs/gearSystem" },
        "meta": { "$ref": "urn:sr6forge:common#/$defs/meta" }
      }
    },
    "gearSystem": {
      "type": "object",
      "required": ["type"],
      "additionalProperties": false,
      "properties": {
        "type": {
          "enum": [
            "ACCESSORY", "AMMUNITION", "ARMOR", "ARMOR_ADDITION", "BIOLOGY",
            "BIOWARE", "CHEMICALS", "CYBERWARE", "CODEMODS", "DRONES",
            "ELECTRONICS", "GENETICS", "MAGICAL", "NANOWARE", "SOFTWARE",
            "SURVIVAL", "TOOLS", "VEHICLES", "WEAPON_CLOSE_COMBAT",
            "WEAPON_FIREARMS", "WEAPON_RANGED", "WEAPON_SPECIAL", "IC"
          ]
        },
        "subtype": { "type": "string" },
        "count": { "type": "integer", "minimum": 0 },
        "countable": { "type": "boolean" },
        "availDef": { "type": "string" },
        "avail": { "type": "integer", "minimum": 0 },
        "ammocap": { "type": "integer", "minimum": 0 },
        "ammocount": { "type": "integer", "minimum": 0 },
        "ammoLoaded": { "type": "string" },
        "priceDef": { "type": "string" },
        "price": { "type": "number", "minimum": 0 },
        "customName": { "type": "string" },
        "usedForPool": { "type": "boolean" },
        "notes": { "type": "string" },
        "accessories": { "type": "string" },
        "needsRating": { "type": "boolean" },
        "rating": { "type": "integer", "minimum": 0 },
        "skill": { "type": "string" },
        "skillSpec": { "type": "string" },
        "dmg": { "type": "integer", "minimum": 0 },
        "stun": { "type": "boolean" },
        "dmgDef": { "type": "string" },
        "attackRating": {
          "type": "array",
          "minItems": 5,
          "maxItems": 5,
          "items": { "type": "integer", "minimum": 0 }
        },
        "modes": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "BF": { "type": "boolean" },
            "FA": { "type": "boolean" },
            "SA": { "type": "boolean" },
            "SS": { "type": "boolean" }
          }
        },
        "defense": { "type": "integer" },
        "social": { "type": "integer" },
        "essence": { "type": "number", "minimum": 0 },
        "capacity": { "type": "integer", "minimum": 0 },
        "natural": { "type": "boolean" },
        "a": { "type": "integer" },
        "s": { "type": "integer" },
        "d": { "type": "integer" },
        "f": { "type": "integer" },
        "progSlots": { "type": "integer", "minimum": 0 },
        "handlOn": { "type": "integer" },
        "handlOff": { "type": "integer" },
        "accOn": { "type": "integer" },
        "accOff": { "type": "integer" },
        "spdiOn": { "type": "integer" },
        "spdiOff": { "type": "integer" },
        "tspd": { "type": "integer" },
        "bod": { "type": "integer" },
        "arm": { "type": "integer" },
        "pil": { "type": "integer" },
        "sen": { "type": "integer" },
        "sea": { "type": "integer" },
        "vtype": { "type": "string" },
        "vehicle": { "type": "object" },
        "strWeapon": { "type": "boolean" },
        "dualHand": { "type": "boolean" },
        "genesisID": { "type": "string" },
        "description": { "type": "string" },
        "product": { "type": "string" },
        "page": { "type": "integer", "minimum": 0 },
        "modifier": { "type": "integer" },
        "wild": { "type": "boolean" },
        "pool": { "type": "integer" },
        "isElectronicMatrixDevice": { "type": "boolean" },
        "matrix": { "type": "object" }
      }
    }
  }
}
```

- [ ] **Step 3: Write the failing tests**

Create `validator/__init__.py` and `tests/__init__.py` (both empty).

Create `tests/conftest.py`:

```python
import copy
import pytest

VALID_GEAR_FILE = {
    "book": "corebook",
    "domain": "gear",
    "category": "weapons_firearms",
    "items": [
        {
            "id": "example_autopistol",
            "name": "Example Autopistol",
            "system": {
                "type": "WEAPON_FIREARMS",
                "subtype": "PISTOLS_HEAVY",
                "skill": "firearms",
                "dmg": 3,
                "stun": False,
                "dmgDef": "3P",
                "attackRating": [10, 10, 8, 0, 0],
                "modes": {"SS": False, "SA": True, "BF": False, "FA": False},
                "ammocap": 15,
                "avail": 3,
                "price": 750,
                "description": "A fictional heavy pistol used only for testing.",
            },
            "meta": {
                "book": "corebook",
                "page": 253,
                "extractedAt": "2026-07-25",
                "extractorVersion": "0.1.0",
                "qaStatus": "extracted",
            },
        }
    ],
}


@pytest.fixture
def gear_file():
    return copy.deepcopy(VALID_GEAR_FILE)
```

Create `tests/test_schema.py`:

```python
from pathlib import Path

from validator.model import DataFile
from validator.schema_check import check_file


def df(payload):
    return DataFile(path=Path("data/corebook/gear/weapons_firearms.json"), payload=payload)


def test_valid_file_passes(gear_file):
    assert check_file(df(gear_file)) == []


def test_bad_gear_type_fails(gear_file):
    gear_file["items"][0]["system"]["type"] = "WEAPON_LASER"
    issues = check_file(df(gear_file))
    assert len(issues) == 1
    assert issues[0].rule == "schema"
    assert issues[0].item_id == "example_autopistol"


def test_unknown_system_field_fails(gear_file):
    gear_file["items"][0]["system"]["dmgg"] = 3
    assert any(i.rule == "schema" for i in check_file(df(gear_file)))


def test_attack_rating_wrong_length_fails(gear_file):
    gear_file["items"][0]["system"]["attackRating"] = [10, 10, 8]
    assert any(i.rule == "schema" for i in check_file(df(gear_file)))


def test_missing_meta_field_fails(gear_file):
    del gear_file["items"][0]["meta"]["qaStatus"]
    assert any(i.rule == "schema" for i in check_file(df(gear_file)))


def test_unknown_domain_reports_no_schema(gear_file):
    gear_file["domain"] = "npcs"
    issues = check_file(df(gear_file))
    assert len(issues) == 1
    assert issues[0].rule == "no-schema"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'validator.model'`

- [ ] **Step 5: Implement model + schema_check**

Create `validator/model.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Issue:
    file: str
    item_id: str | None
    rule: str
    message: str


@dataclass
class DataFile:
    path: Path
    payload: dict

    @property
    def book(self) -> str:
        return self.payload.get("book", "")

    @property
    def domain(self) -> str:
        return self.payload.get("domain", "")

    @property
    def category(self) -> str:
        return self.payload.get("category", "")
```

Create `validator/schema_check.py`:

```python
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from validator.model import DataFile, Issue

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


@lru_cache(maxsize=None)
def _registry() -> Registry:
    registry = Registry()
    for schema_path in SCHEMA_DIR.glob("*.schema.json"):
        resource = Resource.from_contents(json.loads(schema_path.read_text(encoding="utf-8")))
        registry = resource @ registry
    return registry


@lru_cache(maxsize=None)
def _validator_for(domain: str) -> Draft202012Validator | None:
    schema_path = SCHEMA_DIR / f"{domain}.schema.json"
    if not schema_path.is_file():
        return None
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=_registry())


def _item_id_for(payload: dict, error_path: list) -> str | None:
    if len(error_path) >= 2 and error_path[0] == "items" and isinstance(error_path[1], int):
        item = payload["items"][error_path[1]]
        if isinstance(item, dict):
            return item.get("id")
    return None


def check_file(df: DataFile) -> list[Issue]:
    validator = _validator_for(df.domain)
    if validator is None:
        return [
            Issue(
                file=str(df.path),
                item_id=None,
                rule="no-schema",
                message=f"no schema for domain {df.domain!r} (expected schemas/{df.domain}.schema.json)",
            )
        ]
    issues = []
    for error in validator.iter_errors(df.payload):
        path = list(error.absolute_path)
        issues.append(
            Issue(
                file=str(df.path),
                item_id=_item_id_for(df.payload, path),
                rule="schema",
                message=f"{'/'.join(str(p) for p in path) or '<root>'}: {error.message}",
            )
        )
    return issues
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_schema.py -v`
Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
git add schemas validator tests requirements.txt requirements-dev.txt pytest.ini
git commit -m "feat: gear + common JSON Schemas with schema-pass checker

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Loader (data-file discovery)

**Files:**
- Create: `validator/loader.py`
- Test: `tests/test_loader.py`

**Interfaces:**
- Consumes: `validator.model.DataFile`, `validator.model.Issue`.
- Produces: `validator.loader.discover(root: Path) -> tuple[list[DataFile], list[Issue]]` — recursively finds `*.json` under `root` (skipping any file named `README.md` is implicit; skip nothing else), parses each; unparseable JSON or non-object root yields an Issue with rule `parse` instead of a DataFile. Results sorted by path.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_loader.py`:

```python
import json

from validator.loader import discover


def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def test_discovers_nested_json(tmp_path, gear_file):
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    write(tmp_path / "corebook" / "gear" / "armor.json", {**gear_file, "category": "armor"})
    files, issues = discover(tmp_path)
    assert issues == []
    assert [f.category for f in files] == ["armor", "weapons_firearms"]
    assert all(f.domain == "gear" for f in files)


def test_bad_json_reports_parse_issue(tmp_path):
    p = tmp_path / "corebook" / "gear" / "broken.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    files, issues = discover(tmp_path)
    assert files == []
    assert len(issues) == 1
    assert issues[0].rule == "parse"


def test_non_object_root_reports_parse_issue(tmp_path):
    write(tmp_path / "corebook" / "gear" / "list.json", [1, 2, 3])
    files, issues = discover(tmp_path)
    assert files == []
    assert issues[0].rule == "parse"


def test_empty_root_ok(tmp_path):
    files, issues = discover(tmp_path)
    assert files == [] and issues == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'validator.loader'`

- [ ] **Step 3: Implement loader**

Create `validator/loader.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from validator.model import DataFile, Issue


def discover(root: Path) -> tuple[list[DataFile], list[Issue]]:
    files: list[DataFile] = []
    issues: list[Issue] = []
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            issues.append(Issue(file=str(path), item_id=None, rule="parse", message=str(exc)))
            continue
        if not isinstance(payload, dict):
            issues.append(
                Issue(file=str(path), item_id=None, rule="parse", message="root must be a JSON object")
            )
            continue
        files.append(DataFile(path=path, payload=payload))
    return files, issues
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_loader.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add validator/loader.py tests/test_loader.py
git commit -m "feat: data-file discovery with parse-error reporting

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Gear sanity rules

**Files:**
- Create: `validator/sanity.py`
- Test: `tests/test_sanity.py`

**Interfaces:**
- Consumes: `DataFile`, `Issue` from `validator.model`.
- Produces: `validator.sanity.check_gear(files: list[DataFile]) -> list[Issue]` — runs all gear rules over already-schema-valid files (callers filter to `domain == "gear"`). Rules and their `Issue.rule` slugs:
  - `duplicate-id` — same item `id` appears twice within one book's gear domain (across files).
  - `damage-format` — `system.dmgDef`, when non-empty, must match `^\d{1,2}[PS](\([a-z]+\))?$` or be `"Special"`.
  - `weapon-fields` — items whose `system.type` starts with `WEAPON_` must have non-empty `system.skill` and non-empty `system.dmgDef`.
  - `plausibility` — `system.avail` ≤ 30 and `system.price` ≤ 10,000,000 when present; `meta.page` ≤ 1500.
  - `path-mismatch` — when the file path ends in `<book>/<domain>/<category>.json`, those three parts must equal the envelope values.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sanity.py`:

```python
import copy
from pathlib import Path

from validator.model import DataFile
from validator.sanity import check_gear


def df(payload, path="data/corebook/gear/weapons_firearms.json"):
    return DataFile(path=Path(path), payload=payload)


def rules(issues):
    return sorted({i.rule for i in issues})


def test_clean_file_no_issues(gear_file):
    assert check_gear([df(gear_file)]) == []


def test_duplicate_id_across_files(gear_file):
    other = copy.deepcopy(gear_file)
    other["category"] = "armor"
    issues = check_gear(
        [df(gear_file), df(other, "data/corebook/gear/armor.json")]
    )
    assert rules(issues) == ["duplicate-id"]


def test_same_id_different_books_ok(gear_file):
    other = copy.deepcopy(gear_file)
    other["book"] = "firing_squad"
    other["items"][0]["meta"]["book"] = "firing_squad"
    issues = check_gear(
        [df(gear_file), df(other, "data/firing_squad/gear/weapons_firearms.json")]
    )
    assert issues == []


def test_bad_damage_code(gear_file):
    gear_file["items"][0]["system"]["dmgDef"] = "3X"
    assert rules(check_gear([df(gear_file)])) == ["damage-format"]


def test_special_damage_ok(gear_file):
    gear_file["items"][0]["system"]["dmgDef"] = "Special"
    assert check_gear([df(gear_file)]) == []


def test_weapon_missing_skill(gear_file):
    gear_file["items"][0]["system"]["skill"] = ""
    assert rules(check_gear([df(gear_file)])) == ["weapon-fields"]


def test_nonweapon_needs_no_skill(gear_file):
    item = gear_file["items"][0]
    item["system"] = {"type": "ELECTRONICS", "avail": 2, "price": 100}
    assert check_gear([df(gear_file)]) == []


def test_implausible_price_and_avail(gear_file):
    gear_file["items"][0]["system"]["price"] = 99_000_000
    gear_file["items"][0]["system"]["avail"] = 99
    assert rules(check_gear([df(gear_file)])) == ["plausibility"]


def test_path_mismatch(gear_file):
    issues = check_gear([df(gear_file, "data/corebook/gear/armor.json")])
    assert rules(issues) == ["path-mismatch"]


def test_path_not_in_convention_is_ignored(gear_file):
    assert check_gear([df(gear_file, "somefile.json")]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_sanity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'validator.sanity'`

- [ ] **Step 3: Implement sanity rules**

Create `validator/sanity.py`:

```python
from __future__ import annotations

import re
from collections import defaultdict

from validator.model import DataFile, Issue

DAMAGE_RE = re.compile(r"^\d{1,2}[PS](\([a-z]+\))?$")
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
    if dmg_def and dmg_def != "Special" and not DAMAGE_RE.match(dmg_def):
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
        return []
    book_part, domain_part, file_part = parts[-3], parts[-2], parts[-1]
    expected = (df.book, df.domain, f"{df.category}.json")
    if domain_part != df.domain:
        return []  # path not following <book>/<domain>/<category>.json convention
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_sanity.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add validator/sanity.py tests/test_sanity.py
git commit -m "feat: gear sanity rules (duplicates, damage codes, weapon fields, plausibility, path)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: CLI (`python -m validator`)

**Files:**
- Create: `validator/cli.py`
- Create: `validator/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `discover`, `check_file`, `check_gear`, `Issue`.
- Produces: `validator.cli.main(argv: list[str] | None = None) -> int` — arg: one path. Pipeline: discover → schema pass per file → sanity pass per domain **only for files with no schema issues**. Prints issues grouped by file (`<rule>` `[item_id]` message), then `OK: N file(s), M item(s) validated` or `FAILED: K issue(s) in N file(s)`. Returns 0 clean, 1 issues, 2 bad path.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
import json

from validator.cli import main


def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def test_clean_tree_exits_zero(tmp_path, gear_file, capsys):
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    assert main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "OK: 1 file(s), 1 item(s) validated" in out


def test_schema_violation_exits_one(tmp_path, gear_file, capsys):
    gear_file["items"][0]["system"]["type"] = "WEAPON_LASER"
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "schema" in out and "FAILED" in out


def test_sanity_violation_exits_one(tmp_path, gear_file, capsys):
    gear_file["items"][0]["system"]["dmgDef"] = "3X"
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    assert main([str(tmp_path)]) == 1
    assert "damage-format" in capsys.readouterr().out


def test_missing_path_exits_two(tmp_path, capsys):
    assert main([str(tmp_path / "nope")]) == 2


def test_schema_invalid_file_skips_sanity(tmp_path, gear_file, capsys):
    gear_file["items"][0]["system"]["dmgg"] = 1
    gear_file["items"][0]["system"]["dmgDef"] = "3X"
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    main([str(tmp_path)])
    out = capsys.readouterr().out
    assert "schema" in out and "damage-format" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'validator.cli'`

- [ ] **Step 3: Implement CLI**

Create `validator/cli.py`:

```python
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
```

Create `validator/__main__.py`:

```python
import sys

from validator.cli import main

sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run full suite**

Run: `.venv\Scripts\python -m pytest -v`
Expected: 25 passed (6 schema + 4 loader + 10 sanity + 5 cli)

- [ ] **Step 5: Commit**

```bash
git add validator/cli.py validator/__main__.py tests/test_cli.py
git commit -m "feat: validator CLI with schema + sanity passes and exit codes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Examples + docs

**Files:**
- Create: `examples/corebook/gear/weapons_firearms.json` (synthetic, committable)
- Modify: `README.md` (Status section + validator usage)
- Test: `tests/test_examples.py`

**Interfaces:**
- Consumes: `validator.cli.main`.
- Produces: a committed, human-readable example of the data format that the validator passes; README instructions a stranger can follow.

- [ ] **Step 1: Write the failing test**

Create `tests/test_examples.py`:

```python
from pathlib import Path

from validator.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_examples_validate_clean(capsys):
    assert main([str(EXAMPLES)]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_examples.py -v`
Expected: FAIL — exit code 2 (examples dir missing)

- [ ] **Step 3: Create the example file**

Create `examples/corebook/gear/weapons_firearms.json` — two invented items showing the format (copy the conftest item, plus one SMG variant):

```json
{
  "book": "corebook",
  "domain": "gear",
  "category": "weapons_firearms",
  "items": [
    {
      "id": "example_autopistol",
      "name": "Example Autopistol",
      "system": {
        "type": "WEAPON_FIREARMS",
        "subtype": "PISTOLS_HEAVY",
        "skill": "firearms",
        "dmg": 3,
        "stun": false,
        "dmgDef": "3P",
        "attackRating": [10, 10, 8, 0, 0],
        "modes": { "SS": false, "SA": true, "BF": false, "FA": false },
        "ammocap": 15,
        "avail": 3,
        "price": 750,
        "description": "A fictional heavy pistol demonstrating the data format. Not from any book."
      },
      "meta": {
        "book": "corebook",
        "page": 1,
        "extractedAt": "2026-07-25",
        "extractorVersion": "0.1.0",
        "qaStatus": "approved"
      }
    },
    {
      "id": "example_smg",
      "name": "Example SMG",
      "system": {
        "type": "WEAPON_FIREARMS",
        "subtype": "SUBMACHINE_GUNS",
        "skill": "firearms",
        "dmg": 4,
        "stun": false,
        "dmgDef": "4P",
        "attackRating": [8, 9, 6, 0, 0],
        "modes": { "SS": false, "SA": true, "BF": true, "FA": true },
        "ammocap": 30,
        "avail": 4,
        "price": 1250,
        "description": "A fictional submachine gun demonstrating fire modes. Not from any book."
      },
      "meta": {
        "book": "corebook",
        "page": 1,
        "extractedAt": "2026-07-25",
        "extractorVersion": "0.1.0",
        "qaStatus": "approved"
      }
    }
  ]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_examples.py -v`
Expected: PASS

- [ ] **Step 5: Update README**

In `README.md`, replace the Status section with:

```markdown
## Using the validator

```bash
pip install -r requirements-dev.txt
python -m validator data/corebook     # validate your local data
python -m validator examples          # validate the committed format examples
pytest                                # run the test suite
```

Every data file must pass two layers: its domain JSON Schema
(`schemas/<domain>.schema.json`) and the domain sanity rules
(duplicate ids, damage-code format, weapon required fields,
plausibility bounds, path/envelope agreement).

## Status

- [x] Gear schema (`schemas/gear.schema.json`) + shared defs (`schemas/common.schema.json`)
- [x] Validator CLI: `python -m validator <path>` — schema pass + sanity pass
- [x] Format examples: `examples/corebook/gear/` (synthetic items only)
- [ ] Extractor (Core Rulebook gear)
- [ ] Review web app
- [ ] Module export

See [docs/design.md](docs/design.md) for the full architecture.
```

- [ ] **Step 6: Full suite + commit**

Run: `.venv\Scripts\python -m pytest -v`
Expected: 26 passed

```bash
git add examples tests/test_examples.py README.md
git commit -m "docs: committed format examples + validator usage; example validation test

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

---

## Self-Review Notes

- **Spec coverage:** design §2 data model → Task 1 schemas; §4 validation both passes → Tasks 1–4; extensibility → domain-keyed `SANITY_CHECKS` dict and per-domain schema files; §7 validator testing → per-rule tests in Task 3. Extractor/web app/export are later plans by design.
- **Type consistency:** `Issue(file, item_id, rule, message)` and `DataFile(path, payload)` used identically in Tasks 1–4; `check_gear` takes `list[DataFile]` everywhere.
- **Placeholder scan:** all steps carry complete code/commands; no TBDs.
