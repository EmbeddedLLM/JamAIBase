import { Base } from "@/resources/base";
import { PollProgressParams, PollProgressParamsSchema, PROGRESS_STATES, ProgressResponse, ProgressResponseSchema } from "@/resources/tasks/types";

export class Tasks extends Base {
    /**
     * Get progress of a task
     * @param key Task key
     * @returns Progress information
     */
    public async getProgress(key: string): Promise<ProgressResponse> {
        const response = await this.httpClient.get("/api/v2/progress", {
            params: { key }
        });

        return this.handleResponse(response, ProgressResponseSchema);
    }

    /**
     * Poll progress until completion or timeout
     * @param key Task key
     * @param params Polling parameters
     * @returns Final progress information or null if timeout
     */
    public async pollProgress(key: string, params?: PollProgressParams): Promise<ProgressResponse | null> {
        const parsedParams = PollProgressParamsSchema.parse(params ?? {});
        const { initialWait = 0.5, maxWait = 1800, verbose = false } = parsedParams;
        const startTime = Date.now();
        let iteration = 1;

        while ((Date.now() - startTime) / 1000 < maxWait) {
            await new Promise((resolve) => setTimeout(resolve, Math.min(initialWait * iteration, 5) * 1000));

            const progress = await this.getProgress(key);
            const state = progress.state;

            if (verbose) {
                console.log(`Progress: key=${key} state=${state || "undefined"}`);
            }

            if (state === PROGRESS_STATES.COMPLETED) {
                return progress;
            } else if (state === PROGRESS_STATES.FAILED) {
                throw new Error(progress.error || "Unknown error");
            }

            iteration++;
        }

        return null;
    }
}
