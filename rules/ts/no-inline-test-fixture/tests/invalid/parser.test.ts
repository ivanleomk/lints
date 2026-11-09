export const sampleYaml = `
version: 1
name: workflow
steps:
  - id: lint
    run: bunx oxlint
  - id: test
    run: bun test
`;
