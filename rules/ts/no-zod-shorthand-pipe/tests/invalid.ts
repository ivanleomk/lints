declare const base: {
  transform(fn: (v: string) => unknown): { pipe(target: unknown): unknown };
};
declare const targetSchema: unknown;

export const shorthand = base.transform((s) => ({ name: s })).pipe(targetSchema);
