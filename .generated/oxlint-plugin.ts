import { rule as r_0 } from "../rules/ts/no-default-config-singleton/rule.ts";
import { rule as r_1 } from "../rules/ts/no-multiline-ternary/rule.ts";
import { rule as r_2 } from "../rules/ts/no-type-assertion/rule.ts";
import { rule as r_3 } from "../rules/ts/no-zod-shorthand-pipe/rule.ts";
import { rule as r_4 } from "../rules/ts/pure-barrel-index/rule.ts";

export default { meta: { name: "lints" }, rules: {
    "no-default-config-singleton": r_0,
    "no-multiline-ternary": r_1,
    "no-type-assertion": r_2,
    "no-zod-shorthand-pipe": r_3,
    "pure-barrel-index": r_4,
}};
