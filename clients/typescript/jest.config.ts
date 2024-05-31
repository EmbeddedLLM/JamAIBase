import type { Config } from "jest";

const config: Config = {
    preset: "ts-jest",
    testEnvironment: "node",
    testMatch: ["**/__tests__/**/*.test.[jt]s?(x)"],
    verbose: true,
    moduleNameMapper: {
        "@/(.*)": "<rootDir>/src/$1",
    },
};

export default config;
