export function firstItem(items: string[]): string {
  const first = items[0];
  if (first === undefined) {
    throw new Error("Expected non-empty items array");
  }
  return first;
}
