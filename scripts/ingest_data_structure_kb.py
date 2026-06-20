# -*- coding: utf-8 -*-
"""Ingest the data-structure Markdown knowledge base into Elasticsearch 8.x."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.vector.elasticsearch_knowledge_base import (  # noqa: E402
    ElasticsearchKnowledgeBaseClient,
    ElasticsearchKnowledgeBaseConfig,
    ElasticsearchKnowledgeBasePipeline,
    HashingTextEmbedder,
    SentenceTransformerEmbedder,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index 数据结构-知识库.md into Elasticsearch with BM25 + HNSW + RRF support."
    )
    parser.add_argument(
        "--file",
        default=os.path.join(ROOT, "数据结构-知识库.md"),
        help="Markdown source file.",
    )
    parser.add_argument(
        "--host",
        default="http://127.0.0.1:9200",
        help="Elasticsearch host URL.",
    )
    parser.add_argument(
        "--index",
        default="eduagent_data_structure_kb",
        help="Elasticsearch index name.",
    )
    parser.add_argument(
        "--dims",
        type=int,
        default=None,
        help="Embedding vector dimensions. Defaults to the chosen model output size.",
    )
    parser.add_argument(
        "--embedding-backend",
        choices=["sentence-transformers", "hashing"],
        default="sentence-transformers",
        help="Embedding backend.",
    )
    parser.add_argument(
        "--embedding-model",
        default="BAAI/bge-small-zh-v1.5",
        help="sentence-transformers model name.",
    )
    parser.add_argument(
        "--embedding-device",
        default=None,
        help="Optional device passed to sentence-transformers, e.g. cpu or cuda.",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Elasticsearch basic-auth username, if security is enabled.",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Elasticsearch basic-auth password, if security is enabled.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the target index before ingesting.",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> ElasticsearchKnowledgeBaseConfig:
    vector_dims = args.dims if args.dims is not None else 512
    return ElasticsearchKnowledgeBaseConfig(
        hosts=[args.host],
        index_name=args.index,
        vector_dims=vector_dims,
        chunk_size_chars=1000,
        chunk_overlap_chars=150,
        basic_auth_user=args.username,
        basic_auth_password=args.password,
        verify_certs=False,
    )


def main() -> int:
    args = parse_args()
    embedder, vector_dims = build_embedder(args)
    config = build_config(args)
    config.vector_dims = vector_dims
    client = ElasticsearchKnowledgeBaseClient(config)
    client.set_embedding_function(embedder.embed, embedder.embed_batch)

    try:
        client.connect()
        pipeline = ElasticsearchKnowledgeBasePipeline(client)
        chunks = pipeline.ingest_markdown_file(
            args.file,
            document_id="data_structure_kb",
            extra_metadata={"course": "数据结构", "retrieval": "bm25+hnsw+rrf"},
            recreate_index=args.recreate,
        )
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        print("Check Elasticsearch host/auth settings and confirm the service is running.", file=sys.stderr)
        return 1
    finally:
        client.close()

    print(f"Indexed {len(chunks)} chunks into index '{config.index_name}'.")
    if chunks:
        print(f"First chunk: {chunks[0].chunk_id} | {chunks[0].title_path}")
    return 0


def build_embedder(args: argparse.Namespace) -> tuple[object, int]:
    if args.embedding_backend == "hashing":
        dims = args.dims or 1024
        embedder = HashingTextEmbedder(dims=dims)
        return embedder, embedder.dims

    embedder = SentenceTransformerEmbedder(
        model_name=args.embedding_model,
        device=args.embedding_device,
    )
    return embedder, embedder.dims


if __name__ == "__main__":
    raise SystemExit(main())
