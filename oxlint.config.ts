import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

interface GeneratedOxlintConfig {
  plugins: string[];
  categories: Record<string, string>;
  hasCustomPlugin: boolean;
  rules: Record<string, unknown>;
  overrides: Array<Record<string, unknown>>;
  ignorePatterns: string[];
}

// Resolve real repository path even when ~/oxlint.config.ts is a symlink.
const realDir = path.dirname(fs.realpathSync(fileURLToPath(import.meta.url)));
const generatedConfigPath = path.join(realDir, ".generated", "oxlint-config.json");
const generatedPluginPath = path.join(realDir, ".generated", "oxlint-plugin.ts");

const generated: GeneratedOxlintConfig = JSON.parse(
  fs.readFileSync(generatedConfigPath, "utf8"),
);

const jsPlugins = generated.hasCustomPlugin ? [generatedPluginPath] : [];

export default {
  plugins: generated.plugins,
  categories: generated.categories,
  jsPlugins,
  rules: generated.rules,
  overrides: generated.overrides,
  ignorePatterns: generated.ignorePatterns,
};
