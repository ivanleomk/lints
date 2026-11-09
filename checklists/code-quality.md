# Model Self-Check: Code Quality

- **Validate at every boundary:** Parse HTTP inputs, CLI args, YAML/JSON files, and DB payloads once at the boundary with canonical schemas (Zod in TS, Pydantic `BaseModel` in Python)—never manual string splitting or ad-hoc dict probing.
- **Zero silent fallbacks or dummy stubs:** Do not swallow errors with `.catch(() => fallback)`, export fallback config singletons, or satisfy interfaces with no-op stubs (`() => undefined`, `() => []`). Remove dead fields from contracts instead.
- **No speculative shims or wrapper types:** Infer types directly from schemas (`z.infer<typeof Schema>`) instead of duplicating `*Input` interfaces, and delete 1-line pass-through wrappers or unused backwards-compatibility layers.
- **Readable spacing & explicit control flow:** Avoid `...(cond ? { k: v } : {})` conditional spread soup and multi-statement one-liners (`a(); b();`). Use explicit `if / else` or `switch / match` blocks and brief 1-line step comments on multi-step flows.
