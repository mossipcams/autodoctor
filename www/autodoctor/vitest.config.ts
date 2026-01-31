import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom",
    include: ["**/*.test.ts"],
    globals: true,
  },
  define: {
    __CARD_VERSION__: JSON.stringify("test"),
  },
});
