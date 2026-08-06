# Attributions

## Software and data sources

| Project | By | Role here |
| --- | --- | --- |
| [shadowrun6-eden](https://github.com/yjeroen/foundry-shadowrun6-eden) | Yeroon; Stefan & Anja Prelle | The Foundry VTT system this project targets. It owns the actor and item data models and derives every computed value at runtime, which is why SR6 Forge writes raw inputs only. Read, never modified. |
| Commlink6 / Genesis ([rpgframework.de](https://rpgframework.de)) | Stefan Prelle | Java character generator for SR6. Its data files supply the structure the printed rules leave implicit — counted accessory mounts, what a quality grants, PACK contents, fake SIN quality levels, per-attribute point pools — and the stable per-item identifiers shared with eden. Read locally from a copy the user installs; nothing from it is redistributed. |
| [@foundryvtt/foundryvtt-cli](https://github.com/foundryvtt/foundryvtt-cli) | Foundry Gaming LLC | Compiles the LevelDB compendium packs. |
| [Quench](https://foundryvtt.com/packages/quench) | Ethaks | In-world integration test runner. |

Shadowrun is a registered trademark of The Topps Company, Inc. Game content is
© Catalyst Game Labs. This project is unaffiliated with either and distributes
no game content: see *What this does not contain* in the README.

## Icon set attributions

Icon sets staged locally under `data/_assets/iconsets/<set>/` for use in the
review app and personal module builds. **The image files are not committed to
this repository** — before any set (or icons from it) is published here or in
a distributed module, verify its license below permits redistribution and add
the required attribution text.

| Local directory | Source | License / attribution status |
| --- | --- | --- |
| `iconsets/cyberpunk-red-core/` | [fvtt-cyberpunk-red-core `src/icons/compendium` (dev branch)](https://gitlab.com/cyberpunk-red-team/fvtt-cyberpunk-red-core/-/tree/dev/src/icons/compendium) | Verify per that repo's LICENSE and icon credits before redistribution |
| `iconsets/ammo-cyberpunk-red/` | Local archive `AMMO_ICONS_CYBERPUNK_RED.zip` | Origin/license to be identified before redistribution |
| `iconsets/blue-generic-scifi/` | Local archive `Icons-Blue-GenericSciFi.zip` | Origin/license to be identified before redistribution |
| `iconsets/red-cyberpunk/` | Local archive `Icons-Red-Cyberpunk.zip` | Origin/license to be identified before redistribution |
| `iconsets/green-imperium-maledictum/` | Local archive `Green-ImperiumMaledictum.zip` | Origin/license to be identified before redistribution |
| *(external)* `C:\Users\johnb\Downloads\icons` | Personal icon library (mixed sources, incl. game-icons.net-style SVGs) | game-icons.net assets are CC BY 3.0 — attribution required if published |

When a set's provenance is confirmed, replace its status cell with the
license name and the exact attribution line the license requires.
