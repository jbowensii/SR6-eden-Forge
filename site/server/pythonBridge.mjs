import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

export function resolvePython(repoRoot) {
  if (process.env.FORGE_PYTHON) return process.env.FORGE_PYTHON;
  const venv = join(repoRoot, ".venv", "Scripts", "python.exe");
  if (existsSync(venv)) return venv;
  const venvPosix = join(repoRoot, ".venv", "bin", "python");
  if (existsSync(venvPosix)) return venvPosix;
  return "python3";
}

export function runValidator(repoRoot, dataRoot) {
  const python = resolvePython(repoRoot);
  return new Promise((resolve, reject) => {
    execFile(python, ["-m", "validator", dataRoot, "--json"], { cwd: repoRoot }, (error, stdout, stderr) => {
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error(`validator failed: ${stderr || error?.message || "unparseable output"}`));
      }
    });
  });
}
