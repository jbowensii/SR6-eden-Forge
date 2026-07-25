# data/ — local only, never committed

This directory holds extracted game data as JSON, organized as:

```
data/<book>/<domain>/<category>.json
       │        │        └─ e.g. weapons_firearms.json, armor.json
       │        └─ gear, npcs, spells, qualities, ...
       └─ corebook, firing_squad, body_shop, ...
```

Everything under `data/` except this README is **gitignored** because extracted
Shadowrun content is copyrighted. It exists only on machines whose owner has the
source books. To populate it, run the extractor against your own PDFs:

```bash
python -m extractor --book corebook --domain gear --pages 244-290
```
