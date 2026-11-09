declare function useState<T>(initial: T): [T, (next: T) => void];

export const INITIAL_COUNT = 0;

export function Counter() {
  const [count] = useState(INITIAL_COUNT);
  return count;
}
