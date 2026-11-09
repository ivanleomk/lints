import { type RuleDefinition } from "../types.ts";

export const rule: RuleDefinition = {
  meta: {
    type: "problem",
    docs: {
      description: "Disallow `??` and `??=` silent fallbacks.",
    },
  },
  create(context) {
    return {
      LogicalExpression(node) {
        if (node.operator === "??") {
          context.report({
            node,
            message:
              "`??` is banned because nullish coalescing masks missing config and unvalidated inputs. Fix: validate at the boundary (Zod), use a parameter default, or check `if (x === undefined)`. Docs: `lints explain ts/no-nullish-coalescing`.",
          });
        }
      },
      AssignmentExpression(node) {
        if (node.operator === "??=") {
          context.report({
            node,
            message:
              "`??=` is banned because silent fallback mutation masks uninitialized state. Fix: use an explicit `if (x === undefined)` check. Docs: `lints explain ts/no-nullish-coalescing`.",
          });
        }
      },
    };
  },
};
