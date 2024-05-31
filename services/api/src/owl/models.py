import base64
import imghdr
import io
import itertools
from functools import lru_cache

import httpx
import orjson
from langchain.schema.embeddings import Embeddings
from litellm import Router
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from jamaibase.protocol import Chunk, ClipInputData, ModelListConfig
from jamaibase.utils.io import json_loads
from owl.config import get_embed_model_info, get_model_json, get_rerank_model_info


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    cohere_api_base: str = "https://api.cohere.ai/v1"
    jina_api_base: str = "https://api.jina.ai/v1"
    voyage_api_base: str = "https://api.voyageai.com/v1"
    clip_api_base: str = "http://localhost:51010"


def _resolve_provider_model_name(id: str) -> str:
    split_names = id.split("/")
    if len(split_names) < 2:
        raise ValueError("`id` needs to be in the form of provider/model_name")
    # this assume using huggingface model (usually org/model_name)
    return split_names[0], "/".join(split_names[1:])


CONFIG = Config()
HTTP_CLIENT = httpx.Client(timeout=60.0, transport=httpx.HTTPTransport(retries=3))


@lru_cache(maxsize=1)
def _get_embedding_router(model_json: str):
    models = ModelListConfig.model_validate_json(model_json).embed_models
    # refer to https://docs.litellm.ai/docs/routing for more details
    # current fixed strategy to 'simple-shuffle' (no need extra redis, or setting of RPM/TPM)
    return Router(
        model_list=[
            {
                "model_name": m.litellm_id,
                "litellm_params": {
                    "model": m.litellm_id,
                    "api_key": "null",
                    "api_base": None if m.api_base == "" else m.api_base,
                },
            }
            for m in models
        ],
        routing_strategy="simple-shuffle",
    )


# Cached function
def get_embedding_router():
    return _get_embedding_router(get_model_json())


class CloudBase:

    @staticmethod
    def batch(seq, n):
        if n < 1:
            raise ValueError("`n` must be > 0")
        for i in range(0, len(seq), n):
            yield seq[i : i + n]


class CloudReranker(CloudBase):
    API_MAP = {
        "cohere": CONFIG.cohere_api_base,
        "voyage": CONFIG.voyage_api_base,
        "jina": CONFIG.jina_api_base,
    }

    def __init__(self, reranker_name: str, api_key: str = ""):
        """
        Args:
            reranker_name (str): Model name for the Reranker (from v1/model_names)
            api_key (str): api_key for the str of the cloud provider, optional.
        """
        # Get embedder_config
        reranker_config = get_rerank_model_info(reranker_name)
        reranker_config = reranker_config.model_dump(exclude_none=True)
        provider_name, model_name = _resolve_provider_model_name(reranker_config["id"])
        self.provider_name = provider_name
        self.model_name = model_name
        self.reranker_config = reranker_config
        if provider_name not in ["ellm", "cohere", "voyage", "jina"]:
            raise ValueError(
                f"reranker `provider`: {provider_name} not supported please use only following provider: ellm/cohere/voyage/jina"
            )

        api_url = (
            reranker_config["api_base"] + "/rerank"
            if provider_name == "ellm"
            else self.API_MAP[provider_name] + "/rerank"
        )
        self.reranking_args = {
            "model": self.model_name,
            "api_key": api_key,
            "api_url": api_url,
        }

    def rerank_chunks(
        self,
        chunks: list[Chunk],
        query: str,
        batch_size: int = 256,
        title_weight: float = 0.6,
        content_weight: float = 0.4,
        use_concat: bool = False,
    ) -> list[tuple[Chunk, float, int]]:
        if self.provider_name == "voyage":
            batch_size = 32  # voyage has a limit on token lengths 100,000
        all_contents = [d.text for d in chunks]
        all_titles = [d.title for d in chunks]
        if use_concat:
            all_concats = [
                "Title: " + _title + "\nContent: " + _content
                for _title, _content in zip(all_titles, all_contents)
            ]
            concat_scores = self._rerank_by_batch(query, all_concats, batch_size)
            scores = [x["relevance_score"] for x in concat_scores]
        else:
            content_scores = self._rerank_by_batch(query, all_contents, batch_size)
            title_scores = self._rerank_by_batch(query, all_titles, batch_size)
            scores = [
                (
                    c["relevance_score"] * content_weight + t["relevance_score"] * title_weight
                    if chunks[idx].title != ""
                    else 0.0
                )
                for idx, (c, t) in enumerate(zip(content_scores, title_scores))
            ]
        reranked_chunks = sorted(
            ((d, s, i) for i, (d, s) in enumerate(zip(chunks, scores))),
            key=lambda x: x[1],
            reverse=True,
        )
        logger.info(f"Reranked order: {[r[2] for r in reranked_chunks]}")
        return reranked_chunks

    def _rerank(self, query, documents: list[str]) -> list[dict]:
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

        response = HTTP_CLIENT.post(self.reranking_args["api_url"], headers=headers, json=data)
        if response.status_code != 200:
            raise RuntimeError(response.text)
        response = json_loads(response.text)
        if self.provider_name == "voyage":
            return response["data"]
        else:
            return response["results"]

    def _rerank_by_batch(self, query, documents: list[str], batch_size: int) -> list[dict]:
        all_data = []
        for document in self.batch(documents, batch_size):
            _tmp = self._rerank(
                query, document
            )  # this scores might not be sorted by input index. some provider will sort result by relevance score
            _tmp = sorted(_tmp, key=lambda x: x["index"], reverse=False)  # sort by index
            all_data.extend(_tmp)
        return all_data


class CloudEmbedder(CloudBase, Embeddings):
    def __init__(self, embedder_name: str, api_key: str = ""):
        """
        Args:
            embedder_name (str): Model Name for the Embedder (from v1/model_names)
            api_key (str): api_key for embedder
        """
        # Get embedder_config
        embedder_config = get_embed_model_info(embedder_name)
        embedder_config = embedder_config.model_dump(exclude_none=True)
        provider_name, model_name = _resolve_provider_model_name(embedder_config["id"])
        self.provider_name = provider_name
        self.model_name = "voyage/" + model_name if provider_name == "voyage" else model_name
        self.embedder_config = embedder_config
        if provider_name not in ["ellm", "openai", "cohere", "voyage", "jina"]:
            raise ValueError(
                f"embedder `provider`: {provider_name} not supported please use only following provider: ellm/openai/cohere/voyage/jina"
            )
        self.embedding_args = {
            "model": embedder_config["litellm_id"],
            "api_key": api_key,
            "dimensions": self.embedder_config.get("dimensions"),
        }

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if self.provider_name == "jina":
            embedding_resp = self._embed_jina(texts)
        else:
            embedding_resp = get_embedding_router().embedding(**self.embedding_args, input=texts)
        return [x["embedding"] for x in embedding_resp.json()["data"]]

    def _embed_jina(self, texts: list[str]) -> httpx.Response:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.embedding_args['api_key']}",
        }
        data = {"input": texts, "model": self.embedding_args["model"]}

        response = HTTP_CLIENT.post(
            CONFIG.jina_api_base + "/embeddings",
            headers=headers,
            json=data,
        )
        if response.status_code != 200:
            raise RuntimeError(response.text)
        return response

    def embed_documents(self, texts: list[str], batch_size: int = 2048) -> list[list[float]]:
        """Embed search docs."""
        if not isinstance(texts, list):
            raise TypeError("`texts` must be a list.")
        if self.provider_name == "cohere":
            self.embedding_args["input_type"] = "search_document"
            batch_size = 96  # limit on cohere server
        if self.provider_name == "jina":
            batch_size = 128  # don't know limit, but too large will timeout
        if self.provider_name == "voyage":
            batch_size = 128  # limit on voyage server
        embeddings = [self._embed(txt) for txt in self.batch(texts, batch_size)]
        return list(itertools.chain(*embeddings))

    def embed_query(self, text: str) -> list[float]:
        """Embed query text."""
        if not isinstance(text, str):
            raise TypeError("`text` must be a str.")
        if self.embedding_args.get("transform_query"):
            text = self.embedding_args.get("transform_query") + text
        if self.provider_name == "cohere":
            self.embedding_args["input_type"] = "search_query"
        embeddings = self._embed([text])
        return embeddings[0]  # should just have 1 elements


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
        api_url = CONFIG.clip_api_base + "/post"
        self.embedding_args = {
            "api_url": api_url,
        }

    def _embed(self, objects: list[ClipInputData]) -> list[list[float]]:
        parsed_data = self._parse_data(objects)
        headers = {"Content-Type": "application/json"}
        data = {"data": parsed_data, "execEndpoint": "/"}
        response = HTTP_CLIENT.post(
            self.embedding_args["api_url"],
            headers=headers,
            data=orjson.dumps(data),
        )
        if response.status_code != 200:
            raise RuntimeError(response.text)
        return [x["embedding"] for x in response.json()["data"]]

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
            except Exception:
                raise OSError(f"object {data.image_filename} is not a valid image format.")
            # Read the image file
            img_data = f.read()
            img_base64 = base64.b64encode(img_data)
            data_uri = f"data:image/{img_format};base64," + img_base64.decode("utf-8")
        return data_uri

    def embed_documents(
        self, objects: list[ClipInputData], batch_size: int = 64
    ) -> list[list[float]]:
        """Embed search objects (image)."""
        if not isinstance(objects, list):
            raise TypeError("`objects` must be a list.")
        embeddings = [self._embed(obj) for obj in self.batch(objects, batch_size)]
        return list(itertools.chain(*embeddings))

    def embed_query(self, data: ClipInputData) -> list[float]:
        """Embed query text/image."""
        embeddings = self._embed([data])
        return embeddings[0]  # should just have 1 elements
