# import numpy as np
# import pytest

# from owl.protocol import Chunk
# from owl.models import (
#     BgeEmbedder,
#     BgeReranker,
#     Embedder,
#     MiniLMv2Embedder,
#     Reranker,
#     TinyBertReranker,
# )


# def test_from_pretrained():
#     embedder = Embedder.from_pretrained("EmbeddedLLM/bge-base-en-v1.5-onnx-o4-o2-gpu")
#     assert isinstance(embedder, BgeEmbedder)
#     embedder = Embedder.from_pretrained("EmbeddedLLM/bge-base-en-v1.5-onnx-o3-cpu")
#     assert isinstance(embedder, BgeEmbedder)
#     embedder = Embedder.from_pretrained("EmbeddedLLM/all-MiniLM-L6-v2-onnx-o3-cpu")
#     assert isinstance(embedder, MiniLMv2Embedder)

#     reranker = Reranker.from_pretrained("EmbeddedLLM/bge-reranker-base-onnx-o4-o2-gpu")
#     assert isinstance(reranker, BgeReranker)
#     reranker = Reranker.from_pretrained("EmbeddedLLM/bge-reranker-base-onnx-o3-cpu")
#     assert isinstance(reranker, BgeReranker)
#     reranker = Reranker.from_pretrained("EmbeddedLLM/ms-marco-TinyBERT-L-2-v2-onnx-o3-cpu")
#     assert isinstance(reranker, TinyBertReranker)


# @pytest.mark.parametrize("model", ["EmbeddedLLM/all-MiniLM-L6-v2-onnx-o3-cpu"])
# def test_embedder(model: str):
#     query = "The llama (/ˈlɑːmə/) (Lama glama) is a domesticated South American camelid."

#     embedder = Embedder.from_pretrained(model)
#     output_batched = np.array(embedder.embed_documents([query] * 16))
#     output_single = np.array(embedder.embed_query(query)).reshape(1, -1)
#     assert np.amax(np.abs(output_batched - output_single)) < 0.0003


# @pytest.mark.parametrize("model", ["EmbeddedLLM/ms-marco-TinyBERT-L-2-v2-onnx-o3-cpu"])
# def test_reranker(model: str):
#     sentences = [
#         "If you want to fly a single-line kite, wait for a day when winds are between 5 and 25 mph.",
#         "The llama (/ˈlɑːmə/) (Lama glama) is a domesticated South American camelid.",
#         "The alpaca (Lama pacos) is a species of South American camelid mammal.",
#     ]
#     chunks = [Chunk(text=s, title=s) for s in sentences]
#     reranker = Reranker.from_pretrained(model)
#     chunks = reranker.rerank_chunks(chunks, query="What is a harimau?")
#     assert "kite" in chunks[-1][0].text
