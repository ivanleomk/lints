interface User {
  id: string;
}

export function castUser(raw: unknown): User {
  return raw as User;
}
