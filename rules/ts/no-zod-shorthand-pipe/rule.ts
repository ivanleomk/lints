import { type RuleDefinition } from "../types.ts";

export const rule: RuleDefinition = {
  meta: {
    type: "problem",
    docs: {
      description: "Disallow `.transform(...).pipe(...)` string-shorthand coercions.",
    },
  },
  create(context) {
    return {
      CallExpression(node) {
        const callee = node.callee;
        if (
          callee &&
          callee.type === "MemberExpression" &&
          callee.property &&
          callee.property.type === "Identifier" &&
          callee.property.name === "pipe" &&
          callee.object &&
          callee.object.type === "CallExpression" &&
          callee.object.callee &&
          callee.object.callee.type === "MemberExpression" &&
          callee.object.callee.property &&
          callee.object.callee.property.type === "Identifier" &&
          callee.object.callee.property.name === "transform"
        ) {
          context.report({
            node,
            message:
              "`.transform(...).pipe(...)` shorthand coercions are banned. Fix: define explicit fields on a canonical `z.object({ ... })` schema. Docs: `lints explain ts/no-zod-shorthand-pipe`.",
          });
        }
      },
    };
  },
};
