from __future__ import annotations

import argparse
import time

from pinecone import ServerlessSpec

from .config import get_settings
from .pinecone_rag import PINECONE_DIMENSION, _embedding_values, _index, _pinecone_client, build_playbook_documents


def main() -> None:
    parser = argparse.ArgumentParser(description="Index the approved response playbook in Pinecone")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the configured index")
    args = parser.parse_args()
    settings = get_settings()
    client = _pinecone_client(settings)
    indexes = client.list_indexes()
    names = {
        item["name"] if isinstance(item, dict) else getattr(item, "name", str(item))
        for item in indexes
    }
    if args.recreate and settings.pinecone_index_name in names:
        client.delete_index(settings.pinecone_index_name)
        names.remove(settings.pinecone_index_name)
    if settings.pinecone_index_name not in names:
        client.create_index(
            name=settings.pinecone_index_name,
            dimension=PINECONE_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud=settings.pinecone_cloud, region=settings.pinecone_region),
        )
        for _ in range(60):
            description = client.describe_index(settings.pinecone_index_name)
            status = getattr(description, "status", {})
            if isinstance(status, dict) and status.get("ready"):
                break
            time.sleep(2)
    index = _index(settings, client)
    records = []
    for document in build_playbook_documents():
        embedding = client.inference.embed(
            model=settings.pinecone_embedding_model,
            inputs=[document["text"]],
            parameters={"input_type": "passage", "truncate": "END"},
        )
        records.append({
            "id": document["id"],
            "values": _embedding_values(embedding),
            "metadata": {**document["metadata"], "text": document["text"]},
        })
    index.upsert(vectors=records, namespace=settings.pinecone_namespace)
    print(f"Indexed {len(records)} approved playbook documents in {settings.pinecone_index_name}:{settings.pinecone_namespace}")


if __name__ == "__main__":
    main()
