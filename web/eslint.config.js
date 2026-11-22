import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'

/**
 * ESLint 配置：主要目的是把「模块边界」变成会报错的规则。
 *
 * 约束 3：features 下的模块不能互相 import。
 *   chat 里不能出现 trip 的东西，反之亦然。
 *   要共用，把代码挪到 shared/。
 *
 *   为什么用规则来卡而不是靠自觉：
 *   页面一多，最容易发生的事就是「顺手 import 一下」。
 *   等到两个模块互相引用，改一个就会牵动另一个，那时候再拆就晚了。
 */
export default [
  {
    ignores: ['dist/**', 'node_modules/**'],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],

  // .vue 文件里的 <script setup lang="ts"> 要用 TS 解析器，
  // 否则 eslint 会把类型标注当成语法错误。
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
        extraFileExtensions: ['.vue'],
      },
    },
  },

  {
    files: ['**/*.{ts,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
    },
    rules: {
      // ---------- 代码质量 ----------
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',

      // ---------- Vue ----------
      'vue/multi-word-component-names': 'off', // 组件名用中文概念，不必强行多单词
      'vue/require-default-prop': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
    },
  },

  // ---------- 约束：features 之间不能互相引用 ----------
  {
    files: ['src/features/chat/**/*'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['../trip/*', '../trip/**', '**/features/trip/**', '../customer/*', '**/features/customer/**'],
              message:
                '对话模块不能引用出行/客服模块。确实要共用的代码，请挪到 src/shared/。',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['src/features/trip/**/*'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['../chat/*', '../chat/**', '**/features/chat/**', '../customer/*', '**/features/customer/**'],
              message:
                '出行模块不能引用对话/客服模块。确实要共用的代码，请挪到 src/shared/。',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['src/features/customer/**/*'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['../chat/*', '../chat/**', '**/features/chat/**', '../trip/*', '**/features/trip/**'],
              message:
                '客服模块不能引用对话/出行模块。确实要共用的代码，请挪到 src/shared/。',
            },
          ],
        },
      ],
    },
  },

  // ---------- 约束：shared 不能反过来依赖 features ----------
  {
    files: ['src/shared/**/*'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['../features/*', '../features/**', '**/features/**'],
              message: 'shared/ 是底层，不能反过来引用 features/ 里的东西。',
            },
          ],
        },
      ],
    },
  },
]

