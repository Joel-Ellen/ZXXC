import js from "@eslint/js";
import globals from "globals";
import pluginVue from "eslint-plugin-vue";

export default [
  {
    ignores: [
      "coverage/**",
      "dist/**",
      "node_modules/**",
      "output/**",
      ".mermaid-runtime/**",
      "**/*.d.ts",
      "**/*.ts",
    ],
  },
  js.configs.recommended,
  ...pluginVue.configs["flat/essential"],
  {
    files: ["**/*.{js,mjs,cjs,vue}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
    },
    rules: {
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          caughtErrors: "none",
          varsIgnorePattern: "^_",
        },
      ],
    },
  },
  {
    files: ["*.config.js", "vite.config.js"],
    languageOptions: {
      globals: globals.node,
    },
  },
  {
    files: ["**/*.{spec,test}.js", "tests/**/*.js"],
    languageOptions: {
      globals: {
        ...globals.node,
        ...globals.vitest,
      },
    },
  },
  {
    files: ["src/composables/useEduAgent.js"],
    rules: {
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          caughtErrors: "none",
          varsIgnorePattern: "^(?:_|score$|correctness$|mastery$|mastery_score$)",
        },
      ],
    },
  },
  {
    files: ["src/components/CourseSurveyView.vue", "src/components/LandingView.vue"],
    rules: {
      "vue/no-unused-vars": ["error", { ignorePattern: "^idx$" }],
    },
  },
  {
    files: ["src/components/FloatingChatTray.vue"],
    rules: {
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          caughtErrors: "none",
          varsIgnorePattern: "^(?:_|emit$)",
        },
      ],
    },
  },
  {
    files: ["src/components/LandingView.vue"],
    rules: {
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          caughtErrors: "none",
          varsIgnorePattern: "^(?:_|watch$)",
        },
      ],
    },
  },
];
