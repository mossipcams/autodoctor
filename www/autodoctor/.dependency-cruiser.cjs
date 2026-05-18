/** @type {import("dependency-cruiser").IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      comment: "Keep the card module graph acyclic.",
      severity: "error",
      from: {},
      to: {
        circular: true,
      },
    },
    {
      name: "not-to-dev-dependency",
      comment: "Runtime code must not depend on dev-only packages.",
      severity: "error",
      from: {
        pathNot: "\\.test\\.ts$|^vitest\\.config\\.ts$|^quality-checks\\.mjs$",
      },
      to: {
        dependencyTypes: ["npm-dev"],
      },
    },
    {
      name: "no-orphans",
      comment: "Keep source files connected to an entrypoint or test.",
      severity: "warn",
      from: {
        orphan: true,
        pathNot:
          "^autodoctor-card\\.ts$|^autodoctor-card\\.js$|\\.test\\.ts$|^vitest\\.config\\.ts$|^rollup\\.config\\.js$|^quality-checks\\.mjs$|^\\.dependency-cruiser\\.cjs$",
      },
      to: {},
    },
  ],
  options: {
    doNotFollow: {
      path: "node_modules",
    },
    includeOnly: "^((?!node_modules).)*$",
    tsConfig: {
      fileName: "tsconfig.json",
    },
  },
};
