import { readFileSync } from "fs";
import { resolve as resolvePath } from "path";
import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import terser from "@rollup/plugin-terser";
import replace from "@rollup/plugin-replace";

const manifest = JSON.parse(
  readFileSync(
    resolvePath("../../custom_components/autodoctor/manifest.json"),
    "utf-8",
  ),
);

export default {
  input: "autodoctor-card.ts",
  output: {
    file: "autodoctor-card.js",
    format: "es",
    inlineDynamicImports: true,
  },
  plugins: [
    replace({
      preventAssignment: true,
      __CARD_VERSION__: JSON.stringify(manifest.version),
    }),
    resolve(),
    typescript(),
    terser(),
  ],
};
