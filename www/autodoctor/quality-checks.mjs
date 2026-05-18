import { spawnSync } from "node:child_process";

const scripts = ["lint:deps", "lint:deadcode", "lint:duplicates"];

for (const script of scripts) {
  const result = spawnSync("npm", ["run", script], {
    stdio: "inherit",
    shell: process.platform === "win32",
  });

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}
