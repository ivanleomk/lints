import { type RuleDefinition } from "../types.ts";

export const rule: RuleDefinition = {
  meta: {
    type: "problem",
    docs: {
      description: "Disallow multi-line `? ... : ...` ternaries in `.ts` logic.",
    },
  },
  create(context) {
    return {
      ConditionalExpression(node) {
        if (node.loc && node.loc.start.line !== node.loc.end.line) {
          context.report({
            node,
            message:
              "Multi-line `? ... : ...` ternaries are banned in logic modules. Fix: rewrite as an explicit `if / else` block or `switch / case`. Docs: `lints explain ts/no-multiline-ternary`.",
          });
        }
      },
    };
  },
};
