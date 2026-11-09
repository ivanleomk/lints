import { type RuleDefinition } from "../types.ts";

export const rule: RuleDefinition = {
  meta: {
    type: "problem",
    docs: {
      description: "Disallow exported `DEFAULT_*_CONFIG` fallback objects.",
    },
  },
  create(context) {
    return {
      ExportNamedDeclaration(node) {
        if (!node.declaration || node.declaration.type !== "VariableDeclaration") {
          return;
        }
        const declarations = node.declaration.declarations;
        if (!declarations) {
          return;
        }
        for (const decl of declarations) {
          if (
            decl.id &&
            decl.id.type === "Identifier" &&
            decl.id.name &&
            /^DEFAULT_[A-Z0-9_]*CONFIG[A-Z0-9_]*$/.test(decl.id.name) &&
            decl.init &&
            decl.init.type === "ObjectExpression"
          ) {
            context.report({
              node: decl,
              message: `Exported \`${decl.id.name}\` acts as a silent fallback object. Fix: validate required config via a schema or throw a named error when unconfigured. Docs: \`lints explain ts/no-default-config-singleton\`.`,
            });
          }
        }
      },
    };
  },
};
