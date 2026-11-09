export function resolvePort(port: number = 3000): number {
  return port;
}

export function requirePort(port: number | undefined): number {
  if (port === undefined) {
    throw new Error("Missing required port");
  }
  return port;
}
