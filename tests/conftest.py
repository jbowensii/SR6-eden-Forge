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
                "dmg": 2,
                "stun": False,
                "dmgDef": "2P",
                "attackRating": [9, 8, 6, 0, 0],
                "modes": {"SS": False, "SA": True, "BF": False, "FA": False},
                "ammocap": 12,
                "avail": 2,
                "price": 620,
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
