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
