export const ROLES = ["admin", "member"] as const;

export interface User {
  id: string;
}

export function isUser(raw: unknown): raw is User {
  return typeof raw === "object" && raw !== null && "id" in raw && typeof raw.id === "string";
}
