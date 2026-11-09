import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Resolve real repository path even when ~/oxlint.config.mts is a symlink.
const realDir = path.dirname(fs.realpathSync(fileURLToPath(import.meta.url)));
const baseConfig = JSON.parse(
  fs.readFileSync(path.join(realDir, "oxlint.base.json"), "utf8"),
);

// Automatically load any custom JS/ESM plugin files placed in ./plugins/
const pluginsDir = path.join(realDir, "plugins");
const pluginFiles = fs.existsSync(pluginsDir)
  ? fs
      .readdirSync(pluginsDir)
      .filter((file) => file.endsWith(".mjs") || file.endsWith(".js"))
      .toSorted()
      .map((file) => path.join(pluginsDir, file))
  : [];

export default {
  ...baseConfig,
  jsPlugins: [...pluginFiles, ...(baseConfig.jsPlugins ?? [])],
};
