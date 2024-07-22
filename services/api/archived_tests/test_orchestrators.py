import aiohttp
import httpx
from pydantic import ValidationError

from jamaibase import JamAI, protocol
from jamaibase.utils.io import json_loads

CLIENT = JamAI()
MODEL = CLIENT.model_names(prefer="Mistral-7B-Instruct-v0.1", capabilities=["chat"])
MESSAGES = [
    {"role": "system", "content": "You are a concise assistant."},
    {"role": "user", "content": "What is the weather in KL"},
]


async def main():
    async with aiohttp.ClientSession() as session:
        print("\n--- TESTING DOCUMENT EMBED ---")
        async with session.post(
            f"{CLIENT.api_base}/v1/embed_documents",
            json=dict(
                files=[
                    {"uri": "tests/txt/weather.txt", "document_id": "0", "access_level": 0},
                    {
                        "uri": "tests/pptx/(2017.06.30) Neural Machine Translation in Linear Time (ByteNet).pptx",
                        "document_id": "1",
                        "access_level": 0,
                    },
                    {"uri": "s3:///amagpt-test/Demo/constitution_de.pdf"},
                ]
            ),
        ) as response:
            response = await response.text()
        print(response)

        print("\n--- TESTING DOCUMENT RETRIEVAL ---")
        async with session.post(
            f"{CLIENT.api_base}/v1/vector_query",
            json=dict(
                search_query="What is the weather in Iceland?",
                k=3,
                access_level=3,
            ),
        ) as response:
            response = await response.text()
        print(response)

        print("\n--- TESTING MODEL INFO ---")
        async with session.get(f"{CLIENT.api_base}/v1/models") as response:
            response = await response.text()
            models = json_loads(response)["data"]
            models = [
                dict(
                    id=m["id"],
                    context_length=m["context_length"],
                    languages=m["languages"],
                )
                for m in models
            ]
        print(models)
        async with session.get(f"{CLIENT.api_base}/v1/models?model=llama-2-70b-chat") as response:
            response = await response.text()
            models = json_loads(response)["data"]
            models = [
                dict(
                    id=m["id"],
                    context_length=m["context_length"],
                    languages=m["languages"],
                )
                for m in models
            ]
        print(models)

        print("\n--- TESTING LLM STREAMING OUTPUT ---")
        with httpx.Client().stream(
            "POST",
            f"{CLIENT.api_base}/v1/chat/completions",
            json=dict(
                model=MODEL,
                messages=MESSAGES,
                stream=True,
                max_tokens=100,
                temperature=0.1,
            ),
        ) as response:
            for chunk in response.iter_text():
                try:
                    completion = protocol.ChatCompletionChunk.model_validate_json(chunk[5:])
                    print(completion.text, end="", flush=True)
                except Exception:
                    break

        print("\n\n--- TESTING LLM WITH RAG ---")
        async with session.post(
            f"{CLIENT.api_base}/v1/chat/completions",
            json=dict(
                model=MODEL,
                messages=MESSAGES,
                stream=True,
                max_tokens=100,
                rag_params=dict(
                    k=3,
                    access_level=10,
                ),
                temperature=0.1,
            ),
        ) as response:
            references = None
            async for chunk, _ in response.content.iter_chunks():
                try:
                    completion = protocol.ChatCompletionChunk.model_validate_json(chunk[5:])
                    print(completion.text, end="", flush=True)
                    continue
                except ValidationError:
                    pass
                try:
                    references = protocol.References.model_validate_json(chunk[5:])
                except Exception:
                    break
        print(f"\nReferences:")
        for doc in references.documents:
            print(f"--- {doc}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
