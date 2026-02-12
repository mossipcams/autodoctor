import { readFileSync } from "fs";
import { resolve as resolvePath } from "path";
import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import replace from "@rollup/plugin-replace";

const manifest = JSON.parse(
  readFileSync(
    resolvePath("../../custom_components/autodoctor/manifest.json"),
    "utf-8",
  ),
);

export default async () => {
  const plugins = [
    replace({
      preventAssignment: true,
      __CARD_VERSION__: JSON.stringify(manifest.version),
    }),
    resolve(),
    typescript(),
  ];

  if (process.env.AUTODOCTOR_MINIFY === "1") {
    const { default: terser } = await import("@rollup/plugin-terser");
    plugins.push(terser());
  }

  return {
    input: "autodoctor-card.ts",
    output: {
      file: "autodoctor-card.js",
      format: "es",
      inlineDynamicImports: true,
    },
    plugins,
  };
};
