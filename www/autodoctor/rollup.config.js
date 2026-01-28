import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import terser from "@rollup/plugin-terser";

export default {
  input: "autodoctor-card.ts",
  output: {
    file: "autodoctor-card.js",
    format: "es",
    inlineDynamicImports: true,
  },
  plugins: [resolve(), typescript(), terser()],
};
