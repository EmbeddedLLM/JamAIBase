import JamAI from "@/index";
import { GetUrlResponseSchema, UploadFileResponseSchema } from "@/resources/files/types";
import dotenv from "dotenv";
import path from "path";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient File", () => {
    let client: JamAI;
    let testContext: TestContext;
    jest.setTimeout(30000);
    jest.retryTimes(1, {
        logErrorsBeforeRetry: true
    });

    beforeAll(async () => {
        testContext = await setupTestEnvironment();
        client = testContext.client;
    });

    afterAll(async function () {
        await cleanupTestEnvironment(testContext);
    });

    it("file upload by file path, get raw url, get thumb url", async () => {
        const responseUploadFile = await client.file.uploadFile({
            file_path: path.resolve(__dirname, "./embeddedLogo.png")
        });

        const parsedDataUploadFile = UploadFileResponseSchema.parse(responseUploadFile);
        expect(parsedDataUploadFile).toEqual(responseUploadFile);

        const responseGetRawUrls = await client.file.getRawUrls({
            uris: [responseUploadFile.uri]
        });

        const parsedDataGetRawUrl = GetUrlResponseSchema.parse(responseGetRawUrls);
        expect(parsedDataGetRawUrl).toEqual(responseGetRawUrls);

        const responseGetThumbUrls = await client.file.getThumbUrls({
            uris: [responseUploadFile.uri]
        });

        const parsedDataGetThumbUrl = GetUrlResponseSchema.parse(responseGetThumbUrls);
        expect(parsedDataGetThumbUrl).toEqual(responseGetThumbUrls);
    });

    it("audio file upload by file path", async () => {
        const responseUploadFile = await client.file.uploadFile({
            file_path: path.resolve(__dirname, "./zoom-in-audio.mp3")
        });

        const parsedDataUploadFile = UploadFileResponseSchema.parse(responseUploadFile);
        expect(parsedDataUploadFile).toEqual(responseUploadFile);
    });
});
