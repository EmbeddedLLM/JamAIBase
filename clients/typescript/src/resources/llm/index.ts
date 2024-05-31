import { Base } from "@/resources/base";
import {
    ChatCompletionChunk,
    ChatCompletionChunkSchema,
    ChatRequest,
    StreamChatCompletionChunk
} from "@/resources/llm/chat";
import {
    ModelInfoRequest,
    ModelInfoResponse,
    ModelInfoResponseSchema,
    ModelNamesRequest,
    ModelNamesResponse,
    ModelNamesResponseSchema
} from "@/resources/llm/model";

export class LLM extends Base {
    public async modelInfo(params?: ModelInfoRequest): Promise<ModelInfoResponse> {
        let getURL = `/api/v1/models`;

        const response = await this.httpClient.get(getURL, {
            params: params,
            paramsSerializer: {
                indexes: false
            }
        });

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = ModelInfoResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async modelNames(params?: ModelNamesRequest): Promise<ModelNamesResponse> {
        let getURL = `/api/v1/model_names`;

        const response = await this.httpClient.get(getURL, {
            params: params,
            paramsSerializer: {
                indexes: false
            }
        });

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = ModelNamesResponseSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }

    public async generateChatCompletionsStream(params: ChatRequest): Promise<ReadableStream<StreamChatCompletionChunk>> {
        const apiURL = "/api/v1/chat/completions";
        const response = await this.httpClient.post(
            apiURL,
            {
                ...params,
                stream: true
            },
            {
                responseType: "stream"
            }
        );

        const stream = new ReadableStream<StreamChatCompletionChunk>({
            async start(controller: ReadableStreamDefaultController<StreamChatCompletionChunk>) {
                response.data.on("data", (data: any) => {
                    data = data.toString();
                    if (data.endsWith("\n\n")) {
                        const lines = data
                            .split("\n\n")
                            .filter((i: string) => i.trim())
                            .flatMap((line: string) => line.split("\n")); //? Split by \n to handle collation

                        for (const line of lines) {
                            const chunk = line
                                .toString()
                                .replace(/^data: /, "")
                                .replace(/data: \[DONE\]\s+$/, "");

                            if (chunk.trim() == "[DONE]") return;

                            try {
                                const parsedValue = JSON.parse(chunk);
                                controller.enqueue(parsedValue);
                            } catch (err) {
                                console.error("Error parsing:", chunk);
                                continue;
                            }
                        }
                    } else {
                        const chunk = data
                            .toString()
                            .replace(/^data: /, "")
                            .replace(/data: \[DONE\]\s+$/, "");

                        if (chunk.trim() == "[DONE]") return;

                        try {
                            const parsedValue = JSON.parse(chunk);
                            controller.enqueue(parsedValue);
                        } catch (err) {
                            console.error("Error parsing:", chunk);
                        }
                    }
                });

                response.data.on("error", (data: any) => {
                    console.error("error: ", data);
                });

                response.data.on("end", () => {
                    controller.close();
                });
            }
        });

        return stream;
    }

    public async generateChatCompletions(params: ChatRequest): Promise<ChatCompletionChunk> {
        const apiURL = "/api/v1/chat/completions";

        const response = await this.httpClient.post<ChatCompletionChunk>(
            apiURL,
            {
                ...params,
                stream: false
            },
            {}
        );

        return new Promise((resolve, reject) => {
            if (response.status == 200) {
                const parsedData = ChatCompletionChunkSchema.parse(response.data);
                resolve(parsedData);
            } else {
                console.error("Received Error Status: ", response.status);
            }
        });
    }
}
