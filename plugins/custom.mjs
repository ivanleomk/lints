// Central custom Oxlint rules loaded automatically by oxlint.config.mts.
// Enable any rule below inside `oxlint.base.json` under `"rules"`, e.g.:
//   "custom/no- committed-debug": "error"

export default {
  meta: {
    name: "custom",
  },
  rules: {
    "no-debugger-comment": {
      create(context) {
        return {
          DebuggerStatement(node) {
            context.report({
              node,
              message: "Remove `debugger` statement before committing.",
            });
          },
        };
      },
    },
  },
};
