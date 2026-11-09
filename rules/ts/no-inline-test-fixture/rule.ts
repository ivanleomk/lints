import { type RuleDefinition } from "../types.ts";

export const rule: RuleDefinition = {
  meta: {
    type: "problem",
    docs: {
      description: "Move `>= 8`-line inline YAML/JSON/fixture template literals to `tests/assets/`.",
    },
  },
  create(context) {
    return {
      VariableDeclarator(node) {
        if (
          node.id &&
          node.id.type === "Identifier" &&
          node.id.name &&
          /(?:yaml|json|fixture|manifest|payload|sample)/i.test(node.id.name) &&
          node.init &&
          node.init.type === "TemplateLiteral" &&
          node.init.loc &&
          node.init.loc.end.line - node.init.loc.start.line >= 7
        ) {
          context.report({
            node: node.init,
            message:
              "Inline multi-line fixture strings (`>= 8` lines) are banned in tests. Fix: move sample payloads to `tests/assets/` and drive cases with `it.each(...)`. Docs: `lints explain ts/no-inline-test-fixture`.",
          });
        }
      },
    };
  },
};
