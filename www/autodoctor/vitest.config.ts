import { defineConfig } from "vitest/config";
import { VitestReporter } from "tdd-guard-vitest";
import path from "path";

export default defineConfig({
  test: {
    environment: "happy-dom",
    include: ["**/*.test.ts"],
    globals: true,
    reporters: ["default", new VitestReporter(path.resolve(__dirname, "../.."))],
  },
  define: {
    __CARD_VERSION__: JSON.stringify("test"),
  },
});
