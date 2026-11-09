import { type RuleDefinition } from "../types.ts";

export const rule: RuleDefinition = {
  meta: {
    type: "problem",
    docs: {
      description: "Keep barrel `index.ts` files to pure re-exports.",
    },
  },
  create(context) {
    return {
      Program(program) {
        const body = program.body;
        if (!body) {
          return;
        }
        const hasReExport = body.some(
          (stmt) =>
            stmt.type === "ExportAllDeclaration" ||
            (stmt.type === "ExportNamedDeclaration" && stmt.source !== null),
        );
        if (!hasReExport) {
          return;
        }
        for (const stmt of body) {
          if (stmt.type === "ExportNamedDeclaration" && stmt.declaration) {
            context.report({
              node: stmt,
              message:
                "Barrel `index.ts` files that re-export modules must stay pure re-exports. Fix: move inline declarations to a dedicated module (e.g. `types.ts`, `service.ts`) and re-export them here. Docs: `lints explain ts/pure-barrel-index`.",
            });
          }
        }
      },
    };
  },
};
