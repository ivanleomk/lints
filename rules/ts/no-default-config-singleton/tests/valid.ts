export interface RunnerConfig {
  concurrency: number;
}

export function createRunnerConfig(concurrency: number): RunnerConfig {
  if (concurrency <= 0) {
    throw new Error("concurrency must be positive");
  }
  return { concurrency };
}
