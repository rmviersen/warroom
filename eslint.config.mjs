import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Python virtualenv (third-party JS should not be linted)
    "pipeline/venv/**",
  ]),
  {
    rules: {
      // Fetch-on-mount via useCallback + useEffect is standard; rule misfires on async loaders.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
