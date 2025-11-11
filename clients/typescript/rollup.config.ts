import commonjs from "@rollup/plugin-commonjs";
import dynamicImportVars from "@rollup/plugin-dynamic-import-vars";
import json from "@rollup/plugin-json";
import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import copy from "rollup-plugin-copy";
import builtins from "rollup-plugin-node-builtins";
import globals from "rollup-plugin-node-globals";
import polyfillNode from "rollup-plugin-polyfill-node";

export default [
    // Node.js Builds (CJS and ES Modules)
    {
        input: "src/index.ts",
        output: [
            {
                file: "dist/index.cjs.js",
                format: "cjs",
                sourcemap: true,
                inlineDynamicImports: true
            },
            {
                file: "dist/index.mjs",
                format: "es",
                sourcemap: true,
                inlineDynamicImports: true
            }
        ],
        external: [
            "axios",
            "zod",
            "uuid",
            "path",
            "fs",
            "os",
            "agentkeepalive",
            "axios-retry",
            "csv-parser",
            "mime-types",
            "formdata-node",
            "path-browserify"
        ],
        plugins: [
            
            typescript({
                tsconfig: "./tsconfig.json",
                sourceMap: true,
                declaration: true,
                emitDeclarationOnly: false
            }),
            json(),

            resolve({
                browser: false,
                preferBuiltins: true,
                extensions: ['.mjs', '.js', ".ts", '.jsx', '.json', '.sass', '.scss']
            }),
            commonjs(),
            dynamicImportVars(),
            
            copy({
                targets: [
                    { src: "README.md", dest: "dist" },
                    { src: "LICENSE", dest: "dist" },
                    { src: "CHANGELOG.md", dest: "dist" }
                ]
            })
        ]
    },

    // Browser Build (UMD)
    {
        input: "src/index.ts",
        output: {
            file: "dist/index.umd.js",
            format: "umd",
            exports: "named",
            name: "JamAI",
            sourcemap: true,
            inlineDynamicImports: true,
            globals: {
                axios: "axios",
                zod: "zod",
                uuid: "uuid"
            }
        },
        external: ["axios", "zod", "uuid"],
        plugins: [
            
              typescript({
                tsconfig: "./tsconfig.json",
                sourceMap: true,
                declaration: true,
                emitDeclarationOnly: false
            }),
            json(),
            polyfillNode(),
            builtins(),
            globals(),

            resolve({
                browser: true,
                preferBuiltins: false,
                extensions: ['.js', '.ts', '.tsx', '.json']
            }),

            commonjs(),
            dynamicImportVars(),
            
            copy({
                targets: [
                    // Only need to copy once, so you can remove this if already copied
                ]
            })
        ]
    }
];