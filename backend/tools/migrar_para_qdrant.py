"""Migrador LlamaIndex -> Qdrant (SEM reindexar)

Extrai nodes + embeddings do LlamaIndex existente e insere no Qdrant.
NAO recomputa embeddings. NAO altera controle_index.json.

Uso:
    python migrar_para_qdrant.py
"""

import os
import sys
import json
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Migrador")

PASTA_INDICE = "indice"
QDRANT_DIR = "qdrant_data"
COLLECTION_NAME = "jurista_legal_docs"
EMBEDDING_DIM = 384
MIGRATION_LOG = "migration_log.json"
BATCH_SIZE = 100

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct
except ImportError:
    print("Instale: pip install qdrant-client")
    sys.exit(1)

docstore_path = os.path.join(PASTA_INDICE, "docstore.json")
vector_store_path = os.path.join(PASTA_INDICE, "default__vector_store.json")

if not os.path.exists(docstore_path):
    print(f"Erro: {docstore_path} nao encontrado.")
    sys.exit(1)

if not os.path.exists(vector_store_path):
    print(f"Erro: {vector_store_path} nao encontrado.")
    sys.exit(1)

# Controle de migracao
if os.path.exists(MIGRATION_LOG):
    with open(MIGRATION_LOG, "r") as f:
        migration_state = json.load(f)
else:
    migration_state = {"migrated_ids": [], "total_migrated": 0}

migrated_set = set(migration_state.get("migrated_ids", []))
logger.info(f"Migracoes anteriores: {len(migrated_set)} nodes ja migrados")

# Ler docstore
logger.info(f"Lendo {docstore_path}...")
with open(docstore_path, "r", encoding="utf-8") as f:
    docstore_raw = json.load(f)

docstore_data = docstore_raw.get("docstore/data", {})
logger.info(f"Nodes no docstore: {len(docstore_data)}")

# Diagnostico: ver estrutura do primeiro node
if docstore_data:
    first_id = next(iter(docstore_data))
    first_node = docstore_data[first_id]
    logger.info(f"Estrutura do node: {list(first_node.keys())}")
    if "__data__" in first_node:
        logger.info(f"  __data__ keys: {list(first_node['__data__'].keys())}")

# Ler embeddings
logger.info(f"Lendo {vector_store_path}...")
with open(vector_store_path, "r", encoding="utf-8") as f:
    vector_raw = json.load(f)

embedding_dict = vector_raw.get("embedding_dict", {})
logger.info(f"Embeddings no vector store: {len(embedding_dict)}")

# Inicializar Qdrant
logger.info(f"Inicializando Qdrant em: {QDRANT_DIR}")
os.makedirs(QDRANT_DIR, exist_ok=True)
client = QdrantClient(path=QDRANT_DIR)

collections = [c.name for c in client.get_collections().collections]
if COLLECTION_NAME not in collections:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )
    logger.info(f"Collection '{COLLECTION_NAME}' criada")
else:
    info = client.get_collection(COLLECTION_NAME)
    logger.info(f"Collection existente: {info.points_count} pontos")

# Migrar
start_time = time.time()
total_to_migrate = 0
migrated_count = 0
skipped_count = 0
error_count = 0
no_text_count = 0
batch_points = []

for node_id in docstore_data:
    if node_id in embedding_dict:
        total_to_migrate += 1

logger.info(f"Nodes com embedding: {total_to_migrate}")
logger.info(f"A migrar: {total_to_migrate - len(migrated_set)}")
logger.info("=" * 60)

point_id_counter = len(migrated_set)

for node_id, node_data in docstore_data.items():
    if node_id in migrated_set:
        skipped_count += 1
        continue

    if node_id not in embedding_dict:
        continue

    try:
        # CORRECAO: LlamaIndex v0.10+ usa __data__
        data = node_data.get("__data__", node_data)

        text = data.get("text") or data.get("content") or ""

        if not text:
            no_text_count += 1
            if no_text_count <= 3:
                logger.warning(f"Node sem texto: {node_id[:30]}... keys={list(data.keys())[:5]}")
            continue

        metadata = data.get("metadata", {})
        embedding = embedding_dict[node_id]

        if len(embedding) != EMBEDDING_DIM:
            continue

        payload = {
            "text": text,
            "node_id": node_id,
            "author": metadata.get("author", metadata.get("autor", "")),
            "title": metadata.get("title", metadata.get("titulo", "")),
            "year": metadata.get("year", metadata.get("ano", "")),
            "page": metadata.get("page", metadata.get("pagina", "")),
            "chapter": metadata.get("capitulo", metadata.get("chapter", "")),
            "edition": metadata.get("edition", metadata.get("edicao", "")),
            "legal_subject": metadata.get("legal_subject", metadata.get("materia", "")),
            "hash": metadata.get("hash", ""),
            "isbn": metadata.get("isbn", ""),
            "author_id": metadata.get("author_id", ""),
            "work_id": metadata.get("work_id", ""),
            "chapter_id": metadata.get("chapter_id", ""),
            "doctrine_id": metadata.get("doctrine_id", ""),
            "posicao_doutrinaria": metadata.get("posicao_doutrinaria", ""),
            "fonte_normativa": metadata.get("fonte_normativa", ""),
            "orgao_julgador": metadata.get("orgao_julgador", ""),
            "artigo_referenciado": metadata.get("artigo_referenciado", ""),
            "peso_normativo": metadata.get("peso_normativo", 0),
        }

        for k, v in payload.items():
            if v is None:
                payload[k] = ""

        point_id_counter += 1
        batch_points.append(PointStruct(
            id=point_id_counter,
            vector=embedding,
            payload=payload,
        ))

        if len(batch_points) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=batch_points)
            for p in batch_points:
                migrated_set.add(p.payload["node_id"])
            migrated_count += len(batch_points)
            batch_points = []

            if migrated_count % 1000 == 0:
                migration_state["migrated_ids"] = list(migrated_set)
                migration_state["total_migrated"] = migrated_count
                with open(MIGRATION_LOG, "w") as f:
                    json.dump(migration_state, f)
                elapsed = time.time() - start_time
                rate = migrated_count / elapsed if elapsed > 0 else 0
                remaining = (total_to_migrate - migrated_count - skipped_count) / rate if rate > 0 else 0
                logger.info(
                    f"  Migrados: {migrated_count}/{total_to_migrate} "
                    f"({rate:.0f}/s, restante: {remaining/60:.0f}min)"
                )

    except Exception as e:
        error_count += 1
        if error_count <= 5:
            logger.error(f"  Erro node {node_id[:20]}: {e}")

# Batch final
if batch_points:
    client.upsert(collection_name=COLLECTION_NAME, points=batch_points)
    for p in batch_points:
        migrated_set.add(p.payload["node_id"])
    migrated_count += len(batch_points)

# Salvar estado final
migration_state["migrated_ids"] = list(migrated_set)
migration_state["total_migrated"] = migrated_count
with open(MIGRATION_LOG, "w") as f:
    json.dump(migration_state, f)

# Fechar Qdrant corretamente
try:
    client.close()
except Exception:
    pass

elapsed = time.time() - start_time

logger.info("")
logger.info("=" * 60)
logger.info("MIGRACAO CONCLUIDA")
logger.info("=" * 60)
logger.info(f"Nodes migrados: {migrated_count}")
logger.info(f"Nodes pulados (ja migrados): {skipped_count}")
logger.info(f"Nodes sem texto: {no_text_count}")
logger.info(f"Erros: {error_count}")
logger.info(f"Tempo: {elapsed:.0f}s")
logger.info(f"Dados em: {QDRANT_DIR}/")
