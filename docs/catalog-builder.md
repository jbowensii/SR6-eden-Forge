# Shadowrun 6th World Catalog Builder

Turns Shadowrun 6 PDFs you own into a Foundry VTT compendium. No command line.

## Install

Run `SR6CatalogBuilder_Setup_v<version>.exe`. Per-user by default, so no
administrator prompt; it only writes where you already have permission.

Everything needed is inside — Python, the extractors, the review app. The one
thing it will not have is your books.

## Using it

The window asks four questions, then gives you three buttons.

### 1. Where are your PDFs?

Point at the folder holding your Shadowrun 6 books; subfolders are searched
too. It reads back what it found — *"Found 12 books: Sixth World Core Rulebook,
Firing Squad, Street Wyrd and 9 more"* — before anything runs.

Recognition is by the **Catalyst product code** in the filename (`CAT28000`),
falling back to the title, then to distinctive words. A file it cannot place is
listed rather than ignored, so a renamed book is visible instead of quietly
absent.

### 2. Commlink6 *(optional)*

Separate software by Stefan Prelle, from [rpgframework.de](https://rpgframework.de),
under his terms. Not included here and not redistributed. The builder finds an
existing install, or you can point at the jar.

It adds the structure the printed page leaves implicit — how many accessories
fit an item, what a quality hands over, what is inside a PACK. **Skip it and
your PDFs are still read in full.**

Commlink6 data is only used for books whose **PDF you own**. Owning the program
does not unlock content; owning the book does.

### 3. Where is Foundry?

Usually detected. It wants the **Data** folder — the one containing `modules`
and `worlds`. If you moved it with `--dataPath`, browse to it.

### 4. Working folder

Where the extracted library and the built catalog live. Defaults to
`Documents\SR6 Catalog`. Your PDFs are never copied or modified.

---

### Import books

Reads everything. This is the long step — minutes per book — with a live log
and a **Stop** button that actually stops it.

For each book: if Commlink6 has it *and* you own the PDF, its data goes in
first and the PDF fills the gaps. Otherwise the PDF is read on its own.

Where the two disagree about the same field, the disagreement is **recorded on
the item**, not silently resolved, and the item is flagged for review. Two
independent readings of one book, and the places they differ are exactly where
a human should look.

### Review & correct

Opens the review app in your browser. Extraction from a designed page is never
perfect, and **you should not use data in your game you have not looked at**.

Here you can fix a price the OCR fumbled, correct a damage code, repair a
mangled name, write descriptions, assign icons and artwork, and see the exact
Foundry document each item will become. Mark things approved as you go.

Your corrections survive re-imports: item identities are pinned in
`data/_ids/`, so fixing a name later does not change its id or break the
characters linked to it.

### Publish to Foundry

Compiles the compendium packs and installs the **Shadowrun 6th World Catalog**
module. Then enable it in your world under *Game Settings → Manage Modules*.

**Close Foundry first.** Compendium packs are LevelDB and Foundry holds them
open; the builder checks and refuses rather than corrupting a pack. If the
install fails halfway, your previous catalog is put back.

---

## The character generator

The catalog is the library. **SR6 Forge** is the generator that shops from it,
installed separately in Foundry — *Add-on Modules → Install Module*:

```
https://github.com/jbowensii/SR6-eden-Forge/releases/latest/download/module.json
```

It carries rules but no game content, so it works on install and gets its item
text from the catalog you just built.

## Artwork support *(optional)*

Lifting illustrations off the page needs OpenCV and onnxruntime — about 250 MB,
which is why they are not in the main install. Everything else works without
them; items still take icons from your local icon library and you can assign
artwork by hand.

## Where things are

| | |
|---|---|
| Settings | `%APPDATA%\SR6CatalogBuilder\settings.json` |
| Extracted library | `<workspace>\data` |
| Built catalog | `<workspace>\export` |
| Installed module | `<Foundry Data>\modules\sr6-forge-corebook` |

Uninstalling removes the program. It does not touch your workspace, your
settings or your PDFs.

## When something goes wrong

**"No Shadowrun books found"** — the folder has no PDFs the matcher
recognises. Check the unmatched list; a heavily renamed file may need its
product code back in the name.

**"Foundry is running"** — close it, including the launcher window.

**Import stops on one book** — the log names it. One book failing does not
abandon the others; re-run for just that one once you know why.

**A wrong number on the sheet** — that is what the review app is for. Fix it
there and publish again; the fix persists across future imports.

## No game content

Nothing here ships Shadowrun material. The extraction happens on your machine,
from books you bought, and the result stays there. Do not redistribute what it
produces — it is the books in another format.

Shadowrun is a registered trademark of The Topps Company, Inc. Game content is
© Catalyst Game Labs. This project is unaffiliated with either.
