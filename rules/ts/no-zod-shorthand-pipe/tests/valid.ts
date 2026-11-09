declare const z: {
  object(shape: Record<string, unknown>): unknown;
  string(): unknown;
};

export const canonical = z.object({ name: z.string() });
