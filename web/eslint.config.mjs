import js from '@eslint/js';
import prettier from 'eslint-config-prettier/flat';
import tseslint from 'typescript-eslint';

const eslintConfig = [
    js.configs.recommended,
    ...tseslint.configs.recommended,
    prettier,
    {
        files: ['**/*.{ts,tsx}'],
        rules: {
            '@typescript-eslint/no-unused-vars': 'off', // 不检查未使用的变量
            '@typescript-eslint/no-explicit-any': 'off', // 关闭 any 报错
        },
    },
];

export default eslintConfig;
