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

#: Longest edge, in pixels, for an icon copied into the library. Icon sets are
#: commonly authored at 1024px; Foundry draws these as small tiles on a sheet,
#: so the full-size original costs ~1.9 MB apiece — roughly half a gigabyte
#: across one set — for detail no one will ever see. 256 still looks sharp on a
#: high-DPI display at the sizes actually used.
MAX_ICON_PX = 256

#: WebP quality for icons entering the library. Everything shipped is WebP; at
#: 90 it is indistinguishable from the source and a fraction of the bytes.
ICON_QUALITY = 90


def install_icon(source: Path, dest_dir: Path, stem: str,
                 max_px: int = MAX_ICON_PX, quality: int = ICON_QUALITY) -> Path:
    """Put an icon into the library as WebP, shrunk to ``max_px``.

    Returns the file actually written — the extension is NOT the source's, so
    callers must build the stored ``img`` path from the returned name rather
    than assuming one. Getting this wrong records a path that does not exist.

    Vector art is copied verbatim (an SVG has no pixels to shrink or re-encode),
    and if Pillow cannot read the source the original is copied through
    unchanged: an icon that arrives in the wrong format beats no icon at all.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() != ".svg":
        try:
            from PIL import Image                      # optional at import time
            with Image.open(source) as im:
                im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
                if max_px and max(im.size) > max_px:
                    im.thumbnail((max_px, max_px), Image.LANCZOS)
                dest = dest_dir / f"{stem}.webp"
                im.save(dest, format="WEBP", quality=quality, method=4)
                return dest
        except Exception:                              # noqa: BLE001 - see above
            pass
    dest = dest_dir / f"{stem}{source.suffix.lower()}"
    shutil.copyfile(source, dest)
    return dest


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


def load_defaults(data_root: Path) -> dict:
    path = data_root / "_assets" / "generic" / "defaults.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_defaults(data_root: Path, defaults: dict) -> None:
    path = data_root / "_assets" / "generic" / "defaults.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(defaults, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def match_icons(lib_root: Path, data_root: Path, book: str, domain: str, min_score: int = MIN_SCORE) -> dict:
    domain_dir = data_root / book / domain
    lib = index_library(lib_root)
    dest_dir = data_root / "_assets" / book / "lib"
    dest_dir.mkdir(parents=True, exist_ok=True)
    defaults = load_defaults(data_root)
    defaults_changed = False

    matched = generic = missing = 0
    generic_cache: dict[str, str | None] = {}
    for payload_path in sorted(domain_dir.glob("*.json")):
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        changed = False
        for item in payload.get("items", []):
            if item.get("img"):
                continue
            source, score = best_match(item, lib, min_score)
            if source is not None:
                dest = install_icon(source, dest_dir, item["id"])
                item["img"] = f"{book}/lib/{dest.name}"
                print(f"  {item['name']} <- {source.name} (score {score})")
                matched += 1
                changed = True
                continue
            # no name match -> the remembered TYPE/SUBTYPE default, else a
            # freshly-picked generic (which is then remembered)
            itype = str(item["system"].get("type", ""))
            subtype = str(item["system"].get("subtype", ""))
            if not itype and not subtype:
                # An item with no classification has no category to share an
                # icon with. Grouping all of them together produced a generic
                # named ".svg" — an empty slug — which then got stamped onto a
                # hundred unrelated items as if it meant something.
                missing += 1
                continue
            key = f"{itype}/{subtype}"
            if key in defaults and (data_root / "_assets" / defaults[key]).is_file():
                item["img"] = defaults[key]
                generic += 1
                changed = True
                continue
            if key not in generic_cache:
                pick = pick_generic(subtype or itype, lib)
                if pick is None:
                    generic_cache[key] = None
                else:
                    slug = re.sub(r"[^a-z0-9]+", "_", f"{itype}_{subtype}".lower()).strip("_")
                    gdest = install_icon(pick, data_root / "_assets" / "generic", slug)
                    generic_cache[key] = f"generic/{gdest.name}"
                    defaults[key] = generic_cache[key]
                    defaults_changed = True
                    print(f"  [generic {key}] <- {pick.name}")
            if generic_cache[key]:
                item["img"] = generic_cache[key]
                generic += 1
                changed = True
            else:
                missing += 1
        if changed:
            payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if defaults_changed:
        save_defaults(data_root, defaults)
    return {"matched": matched, "generic": generic, "still_missing": missing, "library": len(lib)}

# subtype -> generic search tokens, tried in order when no name match exists.
# "@cyberpunk" biases toward the cyberpunk/ tree of the library.
GENERIC_TERMS: dict[str, list[str]] = {
    "AMMUNITION": ["ammo", "bullet", "magazine"],
    "AMMO_LIGHT": ["ammo", "bullet"], "AMMO_HEAVY": ["ammo", "bullet"],
    "AMMO_RIFLES": ["ammo", "bullet"], "AMMO_TASER": ["ammo", "battery"],
    "AMMO_DARTS": ["dart"], "AMMO_CANNONS": ["shell", "ammo"],
    "AMMO_MACHINE_GUN": ["ammo", "belt", "bullet"], "AMMO_DMSO": ["ammo", "vial"],
    "AMMO_BOLT": ["bolt", "arrow"], "AMMO_INJECTION_BOLT": ["bolt", "syringe"],
    "GRENADES": ["grenade"], "ROCKETS": ["rocket", "missile"], "MISSILES": ["missile", "rocket"],
    "EXPLOSIVES": ["explosive", "dynamite", "bomb"],
    "HOLDOUTS": ["pistol", "@cyberpunk"], "PISTOLS_LIGHT": ["pistol", "@cyberpunk"],
    "PISTOLS_HEAVY": ["pistol", "revolver", "@cyberpunk"], "MACHINE_PISTOLS": ["pistol", "smg", "@cyberpunk"],
    "SUBMACHINE_GUNS": ["smg", "submachine", "@cyberpunk"], "SHOTGUNS": ["shotgun", "@cyberpunk"],
    "RIFLE_ASSAULT": ["rifle", "assault", "@cyberpunk"], "RIFLE_SNIPER": ["sniper", "rifle", "@cyberpunk"],
    "RIFLE_HUNTING": ["rifle", "hunting", "@cyberpunk"], "MACHINE_GUNS": ["machine", "gun", "minigun", "@cyberpunk"],
    "ASSAULT_CANNON": ["cannon", "@cyberpunk"], "LAUNCHERS": ["launcher", "@cyberpunk"],
    "TASERS": ["taser", "stun", "@cyberpunk"], "OTHER_SPECIAL": ["weapon", "gun", "@cyberpunk"],
    "BLADES": ["sword", "knife", "blade"], "CLUBS": ["club", "baton", "mace"],
    "OTHER_CLOSE": ["whip", "knuckles", "melee"], "BOWS": ["bow"], "CROSSBOWS": ["crossbow"],
    "THROWING": ["throwing", "shuriken", "knife"],
    "ARMOR_BODY": ["armor", "vest"], "ARMOR_CLOTHES": ["clothes", "clothing", "jacket"],
    "ARMOR_HELMET": ["helmet"], "ARMOR_SHIELD": ["shield"], "MODIFICATION": ["upgrade", "kit", "armor"],
    "FIREARMS_ACCESSORY": ["scope", "grip", "attachment", "@cyberpunk"],
    "COMMLINK": ["phone", "communicator", "device", "@cyberpunk"],
    "CYBERDECK": ["computer", "laptop", "console", "deck", "@cyberpunk"],
    "ELECTRONIC_ACCESSORIES": ["gadget", "device", "electronic", "@cyberpunk"],
    "RFID": ["chip", "tag", "@cyberpunk"], "COMMUNICATION": ["radio", "antenna", "@cyberpunk"],
    "ID_CREDIT": ["card", "credit", "chip", "@cyberpunk"],
    "OPTICAL": ["binoculars", "goggles", "scope"], "VISION_ENHANCEMENT": ["goggles", "eye", "lens"],
    "AUDIO_ENHANCEMENT": ["headphones", "ear", "audio"], "AUDIO": ["headphones", "microphone", "audio"],
    "SENSOR": ["sensor", "radar", "scanner", "@cyberpunk"], "SECURITY": ["lock", "cuffs", "restraints"],
    "SOFTWARE": ["software", "program", "disk", "chip", "@cyberpunk"],
    "BASIC_PROGRAM": ["program", "chip", "@cyberpunk"], "HACKING_PROGRAM": ["hack", "program", "@cyberpunk"],
    "DATASOFT": ["data", "chip", "@cyberpunk"], "MAPSOFT": ["map", "@cyberpunk"],
    "SHOPSOFT": ["shop", "chip", "@cyberpunk"], "SKILLSOFT": ["chip", "brain", "@cyberpunk"],
    "TEACHSOFT": ["book", "chip", "@cyberpunk"], "AUTOSOFT": ["drone", "chip", "@cyberpunk"],
    "TOOLS": ["tools", "toolbox", "wrench"], "BREAKING": ["lockpick", "crowbar", "tools"],
    "INDUSTRIAL_CHEMICALS": ["chemical", "flask", "barrel"],
    "SURVIVAL_GEAR": ["backpack", "rope", "survival", "camping"], "GRAPPLE_GUN": ["grapple", "hook"],
    "BIOTECH": ["medkit", "medical", "syringe"], "SLAP_PATCHES": ["patch", "bandage", "medical"],
    "CYBERJACK": ["implant", "port", "jack", "@cyberpunk"], "CYBER_HEADWARE": ["brain", "implant", "@cyberpunk"],
    "CYBER_EYEWARE": ["eye", "@cyberpunk"], "CYBER_EARWARE": ["ear", "implant", "@cyberpunk"],
    "CYBER_BODYWARE": ["implant", "cyber", "@cyberpunk"], "CYBER_LIMBS": ["cyberarm", "arm", "prosthetic", "@cyberpunk"],
    "CYBER_LIMB_ACCESSORY": ["arm", "implant", "@cyberpunk"], "CYBER_IMPLANT_WEAPON": ["claw", "blade", "@cyberpunk"],
    "BIOWARE_STANDARD": ["organ", "dna", "bio"], "BIOWARE_CULTURED": ["dna", "brain", "bio"],
    "FOCI_ENCHANTING": ["amulet", "magic"], "FOCI_METAMAGIC": ["amulet", "rune"], "FOCI_POWER": ["orb", "magic"],
    "FOCI_QI": ["talisman", "magic"], "FOCI_SPELL": ["wand", "magic"], "FOCI_SPIRIT": ["totem", "magic"],
    "FOCI_WEAPON": ["sword", "rune"], "MAGICAL_FORMULA": ["scroll", "book"],
    "MAGIC_SUPPLIES": ["herbs", "candle", "pouch"], "MAGIC_LODGE": ["ritual", "candle", "altar"],
    "BIKES": ["motorcycle", "bike"], "CARS": ["car"], "TRUCKS": ["truck", "van"],
    "BOATS": ["boat", "ship"], "SUBMARINES": ["submarine"], "FIXED_WING": ["plane", "aircraft"],
    "ROTORCRAFT": ["helicopter"], "VTOL": ["jet", "aircraft"],
    "MICRODRONES": ["drone"], "MINIDRONES": ["drone"], "SMALL_DRONES": ["drone"],
    "MEDIUM_DRONES": ["drone"], "LARGE_DRONES": ["drone"],
}
FALLBACK_TERMS = ["crate", "box", "bag", "gear"]


def pick_generic(subtype: str, library: list[tuple[Path, set[str]]]):
    """Deterministic shared icon for a subtype: best token overlap with the
    subtype's generic terms ('@cyberpunk' biases the cyberpunk tree)."""
    terms = GENERIC_TERMS.get(subtype, []) or FALLBACK_TERMS
    want = {t for t in terms if not t.startswith("@")}
    bias = {t[1:] for t in terms if t.startswith("@")}
    best, best_score = None, 0
    for path, lib_tokens in library:
        score = len(want & lib_tokens) * 2 + len(bias & lib_tokens)
        if score > best_score or (score == best_score and best and score and len(str(path)) < len(str(best))):
            best, best_score = path, score
    if best is None or not (want & {t for t in tokens(" ".join(best.parts))}):
        # no term hit at all -> ultimate fallback
        for path, lib_tokens in library:
            if set(FALLBACK_TERMS) & lib_tokens:
                return path
        return None
    return best
