import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

/** Where the library actually lives.
 *
 * There are two plausible answers on this machine and they disagree: the repo
 * carries a data/corebook of its own, and the import writes to the user's
 * workspace. The review app already resolved this correctly — SR6_DATA first,
 * then the saved dataDir, then the repo — but the two export CLIs hardcoded
 * join(repoRoot, "data") and nobody noticed, because the repo copy is a real
 * library and exporting it succeeds.
 *
 * That is the failure worth naming: it does not error. It produces a complete,
 * plausible compendium built from a six-day-old snapshot, and the only clue is
 * a row count nobody checks. Both halves of the app now ask the same question
 * and get the same answer.
 */
export function resolveDataRoot(repoRoot) {
  if (process.env.SR6_DATA) return resolve(process.env.SR6_DATA);
  const fallback = join(repoRoot, "data");
  try {
    const settings = JSON.parse(
      readFileSync(join(fallback, "settings.json"), "utf-8"));
    if (settings.dataDir && existsSync(resolve(settings.dataDir))) {
      return resolve(settings.dataDir);
    }
  } catch {
    /* no settings, or unreadable — fall through to the repo copy */
  }
  return fallback;
}
