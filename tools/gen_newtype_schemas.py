"""Generate schema files for the 10 new Eden item domains. Each mirrors the
existing content-domain schema shape (book/domain/category/items; item =
id/name/img/system/meta) with a per-domain system field set drawn from the
shadowrun6-eden template.json. Run once; safe to re-run (idempotent)."""

import json
from pathlib import Path

if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"

    STR = {"type": "string"}
    NUM = {"type": "number"}
    INT = {"type": "integer", "minimum": 0}
    BOOL = {"type": "boolean"}

    COMMON = {  # eden catalog-template + provenance fields every item may carry
        "category": STR, "subtype": STR, "description": STR,
        "product": STR, "page": INT, "genesisID": STR,
    }

    # domain slug -> extra system fields (Eden template field shapes)
    DOMAINS = {
        "complexforms": {"fading": STR, "duration": STR, "skill": STR, "target": STR,
                         "threshold": NUM, "attrib": STR},
        "echoes": {},
        "sprite_powers": {"duration": STR, "isSustained": BOOL, "dmg": NUM, "skill": STR},
        "critter_powers": {"duration": STR, "action": STR, "type": STR, "range": STR},
        "metamagics": {"level": BOOL, "adepts": BOOL, "mages": BOOL},
        "martial_arts": {"techniques": STR,
                         "styleCategory": {"type": "object", "additionalProperties": BOOL}},
        "martial_techniques": {"style": STR, "choice": STR},
        "contacts": {"connection": INT, "loyalty": INT, "favors": INT,
                     "type": STR, "pronouns": STR},
        "sins": {"rating": INT, "quality": STR},
        "foci": {"rating": INT, "force": STR, "bonded": BOOL,
                 "availability": STR, "price": STR, "priceDef": STR},
    }


    def schema_for(domain, extra):
        props = {**COMMON, **extra}
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:sr6forge:{domain}",
            "title": f"SR6-eden-Forge {domain} data file",
            "type": "object",
            "required": ["book", "domain", "category", "items"],
            "additionalProperties": False,
            "properties": {
                "book": {"$ref": "urn:sr6forge:common#/$defs/slug"},
                "domain": {"const": domain},
                "category": {"$ref": "urn:sr6forge:common#/$defs/slug"},
                "items": {"type": "array", "items": {"$ref": "#/$defs/item"}},
            },
            "$defs": {
                "item": {
                    "type": "object",
                    "required": ["id", "name", "system", "meta"],
                    "additionalProperties": False,
                    "properties": {
                        "id": {"$ref": "urn:sr6forge:common#/$defs/slug"},
                        "name": {"type": "string", "minLength": 1},
                        "img": {"type": "string", "minLength": 1},
                        "system": {"type": "object", "additionalProperties": False, "properties": props},
                        "meta": {"$ref": "urn:sr6forge:common#/$defs/meta"},
                    },
                }
            },
        }


    for domain, extra in DOMAINS.items():
        path = SCHEMAS / f"{domain}.schema.json"
        path.write_text(json.dumps(schema_for(domain, extra), indent=2) + "\n", encoding="utf-8")
        print("wrote", path.name)
