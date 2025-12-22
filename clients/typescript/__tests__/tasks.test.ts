import JamAI, { PROGRESS_STATES } from "@/index";
import { afterAll, beforeAll, describe, expect, it, jest } from "@jest/globals";
import dotenv from "dotenv";
import { cleanupTestEnvironment, setupTestEnvironment, TestContext } from "./testUtils";

dotenv.config({
    path: "__tests__/.env"
});

describe("APIClient Tasks", () => {
    let client: JamAI;
    let testContext: TestContext;

    jest.setTimeout(60000); // Increased timeout for real operations
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

    it("get progress for non-existent task", async () => {
        const nonExistentKey = "non-existent-task-key";

        const response = await client.tasks.getProgress(nonExistentKey);

        // For non-existent tasks, the API returns an empty object {}
        // so state will be undefined
        expect(response).toBeDefined();
        // State is optional - for non-existent tasks it will be undefined
        if (response.state !== undefined) {
            expect(Object.values(PROGRESS_STATES)).toContain(response.state);
        }
    });

    it("poll progress with timeout", async () => {
        const nonExistentKey = "non-existent-task-key";

        const response = await client.tasks.pollProgress(nonExistentKey, {
            initialWait: 0.1, // 100ms
            maxWait: 0.5, // 500ms (short timeout for test)
            verbose: false
        });

        // Poll should return null on timeout (since the task doesn't exist and will never complete)
        expect(response).toBeNull();
    });

    it("progress response structure validation", async () => {
        const nonExistentKey = "test-task-key";

        const response = await client.tasks.getProgress(nonExistentKey);

        expect(response).toBeDefined();

        // State is optional - for non-existent tasks it will be undefined
        if (response.state !== undefined) {
            expect(Object.values(PROGRESS_STATES)).toContain(response.state);
        }

        // If error exists, it should be a string
        if (response.error) {
            expect(typeof response.error).toBe("string");
        }

        // If data exists, it can be any type
        if (response.data !== undefined) {
            expect(response.data).toBeDefined();
        }
    });

    it("poll progress with verbose mode", async () => {
        const nonExistentKey = "test-verbose-key";

        const response = await client.tasks.pollProgress(nonExistentKey, {
            initialWait: 0.1,
            maxWait: 0.5,
            verbose: true
        });

        // Poll should return null on timeout for non-existent tasks
        expect(response).toBeNull();
    });



    it("poll progress with different initial wait times", async () => {
        const testKey = "test-initial-wait-key";

        // Test with very short initial wait
        const response1 = await client.tasks.pollProgress(testKey, {
            initialWait: 0.05, // 50ms
            maxWait: 0.3,
            verbose: false
        });

        // Test with longer initial wait
        const response2 = await client.tasks.pollProgress(testKey, {
            initialWait: 0.2, // 200ms
            maxWait: 0.5,
            verbose: false
        });

        // Both should return null on timeout for non-existent tasks
        expect(response1).toBeNull();
        expect(response2).toBeNull();
    });

    // it.skip("track real table import progress", async () => {
    //     const tmpDir = os.tmpdir();
    //     const testTableId = `test_import_${Date.now()}`;
    //     const sourceTableId = `test_source_${Date.now()}`;
    //     const parquetFilePath = path.join(tmpDir, `${testTableId}.parquet`);
    //     let testError: Error | null = null;

    //     // Cleanup any existing tables from previous failed test runs
    //     try {
    //         await client.table.deleteTable({ table_type: "knowledge", table_id: testTableId });
    //     } catch {
    //         // Ignore if table doesn't exist
    //     }
    //     try {
    //         await client.table.deleteTable({ table_type: "knowledge", table_id: sourceTableId });
    //     } catch {
    //         // Ignore if table doesn't exist
    //     }

    //     try {
    //         // Create a simple knowledge table
    //         await client.table.createKnowledgeTable({
    //             id: sourceTableId,
    //             embedding_model: embeddingModel,
    //             cols: [
    //                 {
    //                     id: "text_col",
    //                     dtype: "str"
    //                 },
    //                 {
    //                     id: "number_col",
    //                     dtype: "int"
    //                 }
    //             ]
    //         });

    //         // Add some rows
    //         await client.table.addRow({
    //             table_type: "knowledge",
    //             table_id: sourceTableId,
    //             data: [
    //                 { text_col: "Hello", number_col: 1 },
    //                 { text_col: "World", number_col: 2 }
    //             ]
    //         });

    //         // Export the table to a parquet file
    //         const exportedData = await client.table.exportTable("knowledge", sourceTableId);
    //         await fs.writeFile(parquetFilePath, exportedData);

    //         // Import the table with blocking=false to get a progress key
    //         const fileData = await fs.readFile(parquetFilePath);
    //         const file = new Blob([new Uint8Array(fileData)], { type: "application/octet-stream" }) as any;
    //         file.name = path.basename(parquetFilePath);

    //         const importResponse = await client.table.importTable({
    //             table_type: "knowledge",
    //             file: file,
    //             table_id: testTableId, // This will be the destination table ID
    //             blocking: false
    //         });

    //         console.log("Import response:", importResponse);

    //         // Should have a progress key
    //         expect(importResponse).toHaveProperty("progress_key");
    //         expect(importResponse.progress_key).toBeTruthy();

    //         const progressKey = importResponse.progress_key!;

    //         // Get initial progress
    //         const initialProgress = await client.tasks.getProgress(progressKey);
    //         expect(initialProgress).toBeDefined();

    //         // Should have state
    //         if (initialProgress.state) {
    //             expect(Object.values(PROGRESS_STATES)).toContain(initialProgress.state);

    //             // If it has data, log progress stages for debugging
    //             if (initialProgress.data) {
    //                 console.log("Import progress data:", JSON.stringify(initialProgress.data, null, 2));
    //             }
    //         }

    //         // Poll for completion with verbose mode to see progress updates
    //         const finalProgress = await client.tasks.pollProgress(progressKey, {
    //             initialWait: 0.5,
    //             maxWait: 30, // 30 seconds should be enough for a small import
    //             verbose: true
    //         });

    //         // Should complete successfully
    //         expect(finalProgress).not.toBeNull();
    //         expect(finalProgress?.state).toBe(PROGRESS_STATES.COMPLETED);
    //         expect(finalProgress?.error).toBeUndefined();

    //         // Verify the table was created
    //         const tables = await client.table.listTables({ table_type: "knowledge" });
    //         const importedTable = tables.items.find((t: any) => t.id === testTableId);
    //         expect(importedTable).toBeDefined();
    //         expect(importedTable?.id).toBe(testTableId);
    //     } catch (error) {
    //         console.error("Test failed with error:", error);
    //         testError = error as Error;
    //     } finally {
    //         // Clean up: delete both tables
    //         try {
    //             await client.table.deleteTable({
    //                 table_type: "knowledge",
    //                 table_id: testTableId
    //             });
    //         } catch (cleanupError) {
    //             console.warn("Failed to cleanup test table:", cleanupError);
    //         }
    //         try {
    //             await client.table.deleteTable({
    //                 table_type: "knowledge",
    //                 table_id: sourceTableId
    //             });
    //         } catch (cleanupError) {
    //             console.warn("Failed to cleanup source table:", cleanupError);
    //         }
    //         // Clean up the temporary file
    //         try {
    //             await fs.unlink(parquetFilePath);
    //         } catch (cleanupError) {
    //             // Ignore if file doesn't exist
    //         }

    //         // Re-throw the test error after cleanup
    //         if (testError) {
    //             throw testError;
    //         }
    //     }
    // });
});
