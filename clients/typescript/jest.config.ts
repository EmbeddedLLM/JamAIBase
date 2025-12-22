import type { Config } from "jest";

const config: Config = {
    preset: "ts-jest",
    testEnvironment: "node",
    testMatch: ["**/__tests__/**/*.test.[jt]s?(x)"],
    verbose: true,
    moduleNameMapper: {
        "@/(.*)": "<rootDir>/src/$1"
    },
    transform: {
        "^.+\\.tsx?$": [
            "ts-jest",
            {
                tsconfig: {
                    sourceMap: true,
                    inlineSourceMap: true
                }
            }
        ]
    }
};

export default config;
