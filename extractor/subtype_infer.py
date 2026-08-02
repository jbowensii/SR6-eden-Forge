"""Infer a gear item's Eden subtype when extraction left it blank. Strategy:
match the item's own text (name first, then description + notes) against
ordered keyword/synonym rules per weapon/gear type. Specific patterns come
before general ones ("machine pistol" before "pistol", "grenade launcher" before
"launcher"). Conservative by design: if nothing specific matches, return None and
leave the item blank rather than guess — a wrong subtype is worse than an empty
one. Pure and unit-tested; reused by the importer and the backfill tool."""
from __future__ import annotations

import re

# type -> ordered [(keyword regex, subtype)]; first match wins.
RULES = {
    "WEAPON_FIREARMS": [
        (r"hold[-\s]?out", "HOLDOUTS"),
        (r"machine\s*pistol", "MACHINE_PISTOLS"),
        (r"light\s*pistol", "PISTOLS_LIGHT"),
        (r"heavy\s*pistol", "PISTOLS_HEAVY"),
        (r"submachine|\bsmg\b", "SUBMACHINE_GUNS"),
        (r"shotgun", "SHOTGUNS"),
        (r"assault\s*(rifle|carbine)", "RIFLE_ASSAULT"),
        (r"sniper", "RIFLE_SNIPER"),
        (r"hunting\s*rifle", "RIFLE_HUNTING"),
        (r"assault\s*cannon", "ASSAULT_CANNON"),
        (r"machine\s*gun|\blmg\b|\bhmg\b|\bmmg\b", "MACHINE_GUNS"),
        (r"grenade\s*launcher|missile\s*launcher|rocket\s*launcher|mortar|\blauncher\b", "LAUNCHERS"),
        (r"\btaser\b|stun\s*(gun|baton)", "TASERS"),
        (r"\bcarbine\b|assault\s*rifle", "RIFLE_ASSAULT"),
    ],
    "WEAPON_CLOSE_COMBAT": [
        (r"knife|blade|sword|katana|dagger|machete|\baxe\b|edged|razor|\bspur", "BLADES"),
        (r"club|baton|\bstaff\b|\bmace\b|hammer|\bsap\b|knuckle|nunchaku|\bwhip\b|flail|cudgel|boot", "CLUBS"),
    ],
    "ELECTRONICS": [
        (r"commlink", "COMMLINK"),
        (r"cyberdeck|cyberjack|\bdeck\b|cyberprogram|\bhardening\b|program\s*carrier", "CYBERDECK"),
        (r"\brfid\b|\btag\b", "RFID"),
        (r"credstick|\bsin\b|licen[cs]e|certified\s*cred|passport", "ID_CREDIT"),
        (r"goggle|glasses|\boptic|monocle|contact\s*lens|binocular|scope", "OPTICAL"),
        (r"low[-\s]?light|thermographic|flare\s*comp|image\s*link|smartlink|vision\s*(enhanc|magnif)", "VISION_ENHANCEMENT"),
        (r"earbud|ear\s*plug|audio\s*enhanc|hearing|damper|select\s*sound", "AUDIO_ENHANCEMENT"),
        (r"speaker|micro(phone)?|recorder|\baudio\b", "AUDIO"),
        (r"sensor|detector|scanner|\bcamera\b|motion\s*sense", "SENSOR"),
        (r"radio|transceiver|communication|\bsignal\b|jammer|\bantenna\b", "COMMUNICATION"),
        (r"tool\s*kit|\btoolkit\b|utility\s*kit|\bkit\b", "TOOLS"),
    ],
}


def infer_subtype(type_: str, name: str, description: str = "", notes: str = "") -> str | None:
    """Return an inferred subtype for the given item type, or None if no specific
    keyword matches. Name is checked first (highest confidence), then the prose."""
    rules = RULES.get(type_)
    if not rules:
        return None
    for haystack in (name or "", f"{description or ''} {notes or ''}"):
        low = haystack.lower()
        if not low.strip():
            continue
        for pattern, subtype in rules:
            if re.search(pattern, low):
                return subtype
    return None
