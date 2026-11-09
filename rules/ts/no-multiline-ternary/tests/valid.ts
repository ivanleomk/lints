export function selectEndpoint(isProd: boolean): string {
  if (isProd) {
    return "https://api.example.com";
  }
  return "http://localhost:8080";
}
