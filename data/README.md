# data/ — local only, never committed

This directory holds extracted game data as JSON, organized as:

```
data/<book>/<domain>/<category>.json
       │        │        └─ e.g. weapons_firearms.json, armor.json
       │        └─ gear, npcs, spells, qualities, ...
       └─ corebook, firing_squad, body_shop, ...
```

Two additional local-only trees live here:

```
data/_raw/<book>/pages/p<N>.txt      ← cached page text from YOUR pdf (dump stage)
data/_fixes/<book>_<domain>_fixes.py ← correction tables (renames, manual rows)
```

Everything under `data/` except this README is **gitignored** because extracted
Shadowrun content is copyrighted. It exists only on machines whose owner has the
source books. To populate it, run the extractor against your own PDFs:

```bash
python -m extractor dump --pdf "path/to/book.pdf" --book corebook --pages 245-304
python -m extractor parse --book corebook --domain gear
```

**Back up this directory yourself** (e.g. to a private NAS share) — the fixes
modules represent hours of QA and are not protected by the git repo.
