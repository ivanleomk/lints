declare function useState<T>(initial: T): [T, (next: T) => void];

export function BrokenCounter({ enabled }: { enabled: boolean }) {
  if (enabled) {
    const [count] = useState(0);
    return count;
  }
  return 0;
}
