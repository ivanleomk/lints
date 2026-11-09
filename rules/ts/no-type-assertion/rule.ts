import { type RuleDefinition } from "../types.ts";

export const rule: RuleDefinition = {
  meta: {
    type: "problem",
    docs: {
      description: "Disallow `as T` and `<T>x` type assertions (except `as const`).",
    },
  },
  create(context) {
    return {
      TSAsExpression(node) {
        const ann = node.typeAnnotation;
        if (
          ann &&
          ann.type === "TSTypeReference" &&
          ann.typeName &&
          ann.typeName.type === "Identifier" &&
          ann.typeName.name === "const"
        ) {
          return;
        }
        context.report({
          node,
          message:
            "Type assertions (`as T`) are banned because they bypass runtime validation. Fix: parse with a Zod schema, use a type guard, or parameterize with generics (`as const` is allowed). Docs: `lints explain ts/no-type-assertion`.",
        });
      },
      TSTypeAssertion(node) {
        context.report({
          node,
          message:
            "Angle-bracket type assertions (`<T>x`) are banned. Fix: validate with a Zod schema or narrow via a type guard. Docs: `lints explain ts/no-type-assertion`.",
        });
      },
    };
  },
};
