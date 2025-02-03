import asyncio
import base64
import imghdr
import io
import itertools
from functools import lru_cache

import httpx
import litellm
import orjson
from fastapi import Request
from langchain.schema.embeddings import Embeddings
from litellm import Router
from litellm.router import RetryPolicy
from loguru import logger

from jamaibase.utils.io import json_loads
from owl.configs.manager import ENV_CONFIG
from owl.protocol import (
    Chunk,
    ClipInputData,
    CompletionUsage,
    EmbeddingModelConfig,
    EmbeddingResponse,
    EmbeddingResponseData,
    ExternalKeys,
    ModelListConfig,
    RerankingModelConfig,
)
from owl.utils import select_external_api_key

litellm.drop_params = True
litellm.set_verbose = False
litellm.suppress_debug_info = True

HTTP_CLIENT = httpx.AsyncClient(timeout=60.0, transport=httpx.AsyncHTTPTransport(retries=3))


@lru_cache(maxsize=32)
def _get_embedding_router(model_json: str, external_api_keys: str):
    models = ModelListConfig.model_validate_json(model_json).embed_models
    ExternalApiKeys = ExternalKeys.model_validate_json(external_api_keys)
    # refer to https://docs.litellm.ai/docs/routing for more details
    return Router(
        model_list=[
            {
                "model_name": m.id,
                "litellm_params": {
                    "model": deployment.litellm_id if deployment.litellm_id.strip() else m.id,
                    "api_key": select_external_api_key(ExternalApiKeys, deployment.provider),
                    "api_base": deployment.api_base if deployment.api_base.strip() else None,
                },
            }
            for m in models
            for deployment in m.deployments
        ],
        routing_strategy="latency-based-routing",
        num_retries=3,
        retry_policy=RetryPolicy(
            TimeoutErrorRetries=3,
            RateLimitErrorRetries=3,
            ContentPolicyViolationErrorRetries=3,
            AuthenticationErrorRetries=0,
            BadRequestErrorRetries=0,
            ContextWindowExceededErrorRetries=0,
        ),
        retry_after=5.0,
        timeout=ENV_CONFIG.owl_embed_timeout_sec,
        allowed_fails=3,
        cooldown_time=5.5,
    )


# Cached function
def get_embedding_router(all_models: ModelListConfig, external_keys: ExternalKeys) -> Router:
    return _get_embedding_router(
        model_json=all_models.model_dump_json(),
        external_api_keys=external_keys.model_dump_json(),
    )


class CloudBase:
    @staticmethod
    def batch(seq, n):
        if n < 1:
            raise ValueError("`n` must be > 0")
        for i in range(0, len(seq), n):
            yield seq[i : i + n]

    @staticmethod
    def _resolve_provider_model_name(id: str) -> str:
        split_names = id.split("/")
        if len(split_names) < 2:
            raise ValueError("`id` needs to be in the form of provider/model_name")
        # this assume using huggingface model (usually org/model_name)
        return split_names[0], "/".join(split_names[1:])


class CloudReranker(CloudBase):
    API_MAP = {
        "cohere": ENV_CONFIG.cohere_api_base,
        "voyage": ENV_CONFIG.voyage_api_base,
        "jina": ENV_CONFIG.jina_api_base,
    }

    def __init__(self, request: Request):
        """Reranker router.

        Args:
            request (Request): Starlette request object.

        Raises:
            ValueError: If provider is not supported.
        """
        from owl.billing import BillingManager

        self.request = request
        self.external_keys: ExternalKeys = request.state.external_keys
        self._billing: BillingManager = request.state.billing

    def set_rerank_model(self, reranker_name):
        # Get embedder_config
        reranker_config: RerankingModelConfig = (
            self.request.state.all_models.get_rerank_model_info(reranker_name)
        )
        reranker_config = reranker_config.model_dump(exclude_none=True)
        _, model_name = self._resolve_provider_model_name(reranker_config["id"])
        self.reranker_config = reranker_config
        # 2024-10-03: reranker only support single deployment now.
        deployment = reranker_config["deployments"][0]
        self.provider_name = deployment["provider"]
        if deployment["provider"] not in ["ellm", "cohere", "voyage", "jina"]:
            raise ValueError(
                f"reranker `provider`: {deployment['provider']} not supported please use only following provider: ellm/cohere/voyage/jina"
            )
        api_url = (
            deployment["api_base"] + "/rerank"
            if self.provider_name == "ellm"
            else self.API_MAP[self.provider_name] + "/rerank"
        )
        api_key = select_external_api_key(self.external_keys, self.provider_name)
        self.reranking_args = {
            "model": model_name,
            "api_key": api_key,
            "api_url": api_url,
        }

    async def rerank_chunks(
        self,
        reranker_name: str,
        chunks: list[Chunk],
        query: str,
        batch_size: int = 256,
        title_weight: float = 0.6,
        content_weight: float = 0.4,
        use_concat: bool = False,
    ) -> list[tuple[Chunk, float, int]]:
        self.set_rerank_model(reranker_name)  # configure the reranker to be used
        if self.provider_name == "voyage":
            batch_size = 32  # voyage has a limit on token lengths 100,000
        all_contents = [d.text for d in chunks]
        all_titles = [d.title for d in chunks]
        self._billing.check_reranker_quota(model_id=self.reranker_config["id"])
        if use_concat:
            all_concats = [
                "Title: " + _title + "\nContent: " + _content
                for _title, _content in zip(all_titles, all_contents, strict=True)
            ]
            concat_scores = await self._rerank_by_batch(query, all_concats, batch_size)
            scores = [x["relevance_score"] for x in concat_scores]
        else:
            content_scores = await self._rerank_by_batch(query, all_contents, batch_size)
            title_scores = await self._rerank_by_batch(query, all_titles, batch_size)
            scores = [
                (
                    c["relevance_score"] * content_weight + t["relevance_score"] * title_weight
                    if chunks[idx].title != ""
                    else 0.0
                )
                for idx, (c, t) in enumerate(zip(content_scores, title_scores, strict=True))
            ]
        self._billing.create_reranker_events(
            self.reranker_config["id"],
            len(all_titles) // 100,
        )
        reranked_chunks = sorted(
            ((d, s, i) for i, (d, s) in enumerate(zip(chunks, scores, strict=True))),
            key=lambda x: x[1],
            reverse=True,
        )
        logger.info(f"Reranked order: {[r[2] for r in reranked_chunks]}")
        return reranked_chunks

    async def _rerank(self, query, documents: list[str]) -> list[dict]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": (
                f"Bearer {self.reranking_args['api_key']}"
                if self.provider_name in self.API_MAP.keys()
                else ""
            ),
        }
        data = {
            "model": self.reranking_args["model"],
            "query": query,
            "documents": documents,
            "return_documents": False,
        }

        response = await HTTP_CLIENT.post(
            self.reranking_args["api_url"], headers=headers, json=data
        )
        if response.status_code != 200:
            raise RuntimeError(response.text)
        response = json_loads(response.text)
        if self.provider_name == "voyage":
            return response["data"]
        else:
            return response["results"]

    async def _rerank_by_batch(self, query, documents: list[str], batch_size: int) -> list[dict]:
        all_data = []
        for document in self.batch(documents, batch_size):
            _tmp = await self._rerank(
                query, document
            )  # this scores might not be sorted by input index. some provider will sort result by relevance score
            _tmp = sorted(_tmp, key=lambda x: x["index"], reverse=False)  # sort by index
            all_data.extend(_tmp)
        return all_data


class CloudEmbedder(CloudBase):
    def __init__(self, request: Request):
        """Embedder router.

        Args:
            request (Request): Starlette request object.
        """
        from owl.billing import BillingManager

        self.request = request
        self.external_keys: ExternalKeys = request.state.external_keys
        self._billing: BillingManager = request.state.billing

    def set_embed_model(self, embedder_name):
        # Get embedder_config
        embedder_config: EmbeddingModelConfig = self.request.state.all_models.get_embed_model_info(
            embedder_name
        )
        embedder_config = embedder_config.model_dump(exclude_none=True)
        self.embedder_config = embedder_config
        self.embedder_router = get_embedding_router(
            self.request.state.all_models, self.external_keys
        )
        for deployment in embedder_config["deployments"]:
            if deployment["provider"] not in ["ellm", "openai", "cohere", "voyage", "jina"]:
                raise ValueError(
                    (
                        f"Embedder provider {deployment['provider']} not supported, "
                        "please use only following provider: ellm/openai/cohere/voyage/jina"
                    )
                )
        self.embedding_args = {
            "model": embedder_config["id"],
            "dimensions": self.embedder_config.get("dimensions"),
        }

    async def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        if self.embedder_config["owned_by"] == "jina":
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.external_keys.jina}",
            }
            data = {"input": texts, "model": self.embedding_args["model"]}
            response = await HTTP_CLIENT.post(
                ENV_CONFIG.jina_api_base + "/embeddings",
                headers=headers,
                json=data,
            )
            if response.status_code != 200:
                raise RuntimeError(response.text)
            response = EmbeddingResponse.model_validate_json(response.text)
        else:
            response = await self.embedder_router.aembedding(**self.embedding_args, input=texts)
            response = EmbeddingResponse.model_validate(response.model_dump())

        return response

    async def embed_documents(
        self,
        embedder_name: str,
        texts: list[str],
        batch_size: int = 2048,
    ) -> EmbeddingResponse:
        self.set_embed_model(embedder_name)
        """Embed search docs."""
        if not isinstance(texts, list):
            raise TypeError("`texts` must be a list.")
        if self.embedder_config["owned_by"] == "cohere":
            self.embedding_args["input_type"] = "search_document"
            batch_size = 96  # limit on cohere server
        if self.embedder_config["owned_by"] == "jina":
            batch_size = 128  # don't know limit, but too large will timeout
        if self.embedder_config["owned_by"] == "voyage":
            batch_size = 128  # limit on voyage server
        if self.embedder_config["owned_by"] == "openai":
            batch_size = 256  # limited by token per min (10,000,000)
        self._billing.check_embedding_quota(model_id=self.embedder_config["id"])
        responses = await asyncio.gather(
            *[self.embed_texts(txt) for txt in self.batch(texts, batch_size)]
        )
        embeddings = [e.embedding for e in itertools.chain(*[r.data for r in responses])]
        usages = CompletionUsage(
            prompt_tokens=sum(r.usage.prompt_tokens for r in responses),
            total_tokens=sum(r.usage.total_tokens for r in responses),
        )
        embeddings = EmbeddingResponse(
            data=[EmbeddingResponseData(embedding=e, index=i) for i, e in enumerate(embeddings)],
            model=responses[0].model,
            usage=usages,
        )
        self._billing.create_embedding_events(
            model=self.embedder_config["id"],
            token_usage=usages.total_tokens,
        )
        return embeddings

    async def embed_queries(self, embedder_name: str, texts: list[str]) -> EmbeddingResponse:
        self.set_embed_model(embedder_name)
        """Embed query text."""
        if not isinstance(texts, list):
            raise TypeError("`texts` must be a list.")
        if self.embedding_args.get("transform_query"):
            texts = [self.embedding_args.get("transform_query") + text for text in texts]
        if self.embedder_config["owned_by"] == "cohere":
            self.embedding_args["input_type"] = "search_query"
        self._billing.check_embedding_quota(model_id=self.embedder_config["id"])
        response = await self.embed_texts(texts)
        self._billing.create_embedding_events(
            model=self.embedder_config["id"],
            token_usage=response.usage.total_tokens,
        )
        return response


class CloudImageEmbedder(CloudBase, Embeddings):
    def __init__(self):
        """
        Args:
            client: an httpx client
        Info:
            Read the clip_api_base from the .env directly
            Only use for image embedding
            Query can be text/image
            can be used for text-to-image search or image-to-image search
            DO NOT DO image-to-text-and-image search
            same modality would most certainly always result in a higher scores than different modality obj
        """
        api_url = ENV_CONFIG.clip_api_base + "/post"
        self.embedding_args = {
            "api_url": api_url,
        }

    async def _embed(self, objects: list[ClipInputData]) -> list[list[float]]:
        parsed_data = self._parse_data(objects)
        headers = {"Content-Type": "application/json"}
        data = {"data": parsed_data, "execEndpoint": "/"}
        response = await HTTP_CLIENT.post(
            self.embedding_args["api_url"],
            headers=headers,
            data=orjson.dumps(data),
        )
        if response.status_code != 200:
            raise RuntimeError(response.text)
        return [x["embedding"] for x in json_loads(response)["data"]]

    def _parse_data(self, objects: list[ClipInputData]):
        """
        The objects are list of [ClipInputData]
        """
        return [
            {"uri": self._get_blob_from_data(obj)} if obj.image_filename else {"text": obj.content}
            for obj in objects
        ]

    def _get_blob_from_data(self, data: ClipInputData):
        """get blob from ClipInputData"""
        with io.BytesIO(data.content) as f:
            # Get the image format
            try:
                img_format = imghdr.what(f).lower()
            except Exception as e:
                raise ValueError(
                    f"object {data.image_filename} is not a valid image format."
                ) from e
            # Read the image file
            img_data = f.read()
            img_base64 = base64.b64encode(img_data)
            data_uri = f"data:image/{img_format};base64," + img_base64.decode("utf-8")
        return data_uri

    async def embed_documents(
        self, objects: list[ClipInputData], batch_size: int = 64
    ) -> list[list[float]]:
        """Embed search objects (image)."""
        if not isinstance(objects, list):
            raise TypeError("`objects` must be a list.")
        embeddings = await asyncio.gather(
            *[self._embed(obj) for obj in self.batch(objects, batch_size)]
        )
        return list(itertools.chain(*embeddings))

    async def embed_query(self, data: ClipInputData) -> list[float]:
        """Embed query text/image."""
        embeddings = await self._embed([data])
        return embeddings[0]  # should just have 1 elements
