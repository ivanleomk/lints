export function selectEndpoint(isProd: boolean): string {
  return isProd
    ? "https://api.example.com"
    : "http://localhost:8080";
}
