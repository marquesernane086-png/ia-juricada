"""Migrador LlamaIndex → Qdrant (SEM reindexar)

Extrai nodes + embeddings do LlamaIndex existente e insere no Qdrant.
NAO recomputa embeddings. NAO altera controle_index.json.

Uso:
    python migrar_para_qdrant.py

Requer: pip install qdrant-client llama-index-vector-stores-qdrant
"""

import os
import sys
import json
import logging
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Migrador")

# ============================================================
# CONFIGURACAO
# ============================================================

PASTA_INDICE = "indice"                    # pasta do LlamaIndex atual
QDRANT_DIR = "qdrant_data"                 # pasta do Qdrant destino
COLLECTION_NAME = "jurista_legal_docs"
EMBEDDING_DIM = 384                        # MiniLM multilingual
MIGRATION_LOG = "migration_log.json"       # controle de migracao
BATCH_SIZE = 100                           # inserir em lotes no Qdrant

# ============================================================
# VERIFICACOES
# ============================================================

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
    print("Execute na pasta onde esta o indice LlamaIndex.")
    sys.exit(1)

if not os.path.exists(vector_store_path):
    print(f"Erro: {vector_store_path} nao encontrado.")
    sys.exit(1)

# ============================================================
# CARREGAR CONTROLE DE MIGRACAO
# ============================================================

if os.path.exists(MIGRATION_LOG):
    with open(MIGRATION_LOG, "r") as f:
        migration_state = json.load(f)
else:
    migration_state = {"migrated_ids": [], "total_migrated": 0}

migrated_set = set(migration_state.get("migrated_ids", []))
logger.info(f"Migracoes anteriores: {len(migrated_set)} nodes ja migrados")

# ============================================================
# LER DOCSTORE (nodes com texto e metadata)
# ============================================================

logger.info(f"Lendo {docstore_path}...")
with open(docstore_path, "r", encoding="utf-8") as f:
    docstore_raw = json.load(f)

# LlamaIndex docstore format: {"docstore/data": {node_id: {...}}, ...}
docstore_data = docstore_raw.get("docstore/data", {})
logger.info(f"Nodes no docstore: {len(docstore_data)}")

# ============================================================
# LER VECTOR STORE (embeddings)
# ============================================================

logger.info(f"Lendo {vector_store_path}...")
with open(vector_store_path, "r", encoding="utf-8") as f:
    vector_raw = json.load(f)

# LlamaIndex vector store format: {"embedding_dict": {node_id: [float, ...]}, ...}
embedding_dict = vector_raw.get("embedding_dict", {})
logger.info(f"Embeddings no vector store: {len(embedding_dict)}")

# ============================================================
# INICIALIZAR QDRANT
# ============================================================

logger.info(f"Inicializando Qdrant em: {QDRANT_DIR}")
os.makedirs(QDRANT_DIR, exist_ok=True)
client = QdrantClient(path=QDRANT_DIR)

# Criar collection se nao existe
collections = [c.name for c in client.get_collections().collections]
if COLLECTION_NAME not in collections:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=EMBEDDING_DIM,
            distance=Distance.COSINE,
        ),
    )
    logger.info(f"Collection '{COLLECTION_NAME}' criada")
else:
    info = client.get_collection(COLLECTION_NAME)
    logger.info(f"Collection '{COLLECTION_NAME}' existente: {info.points_count} pontos")

# ============================================================
# MIGRAR NODES
# ============================================================

start_time = time.time()
total_to_migrate = 0
migrated_count = 0
skipped_count = 0
error_count = 0
batch_points = []

# Contar nodes com embeddings
for node_id in docstore_data:
    if node_id in embedding_dict:
        total_to_migrate += 1

logger.info(f"Nodes com embedding: {total_to_migrate}")
logger.info(f"Nodes ja migrados: {len(migrated_set)}")
logger.info(f"Nodes a migrar: {total_to_migrate - len(migrated_set)}")
logger.info("=" * 60)

point_id_counter = len(migrated_set)

for node_id, node_data in docstore_data.items():
    # Pular se ja migrado
    if node_id in migrated_set:
        skipped_count += 1
        continue

    # Pular se nao tem embedding
    if node_id not in embedding_dict:
        continue

    try:
        # Extrair texto
        text = node_data.get("text", "")
        if not text:
            # Tentar campo alternativo
            text = node_data.get("content", "")

        if not text:
            continue

        # Extrair metadata
        metadata = node_data.get("metadata", {})

        # Extrair embedding
        embedding = embedding_dict[node_id]

        if len(embedding) != EMBEDDING_DIM:
            logger.warning(f"  Embedding dim errado: {len(embedding)} (esperado {EMBEDDING_DIM})")
            continue

        # Construir payload para Qdrant
        payload = {
            "text": text,
            "node_id": node_id,
            # Metadata original
            "author": metadata.get("author", metadata.get("autor", "")),
            "title": metadata.get("title", metadata.get("titulo", "")),
            "year": metadata.get("year", metadata.get("ano", "")),
            "page": metadata.get("page", metadata.get("pagina", "")),
            "chapter": metadata.get("capitulo", metadata.get("chapter", "")),
            "edition": metadata.get("edition", metadata.get("edicao", "")),
            "legal_subject": metadata.get("legal_subject", metadata.get("materia", "")),
            "hash": metadata.get("hash", ""),
            "isbn": metadata.get("isbn", ""),
            # Doctrine graph IDs
            "author_id": metadata.get("author_id", ""),
            "work_id": metadata.get("work_id", ""),
            "chapter_id": metadata.get("chapter_id", ""),
            "doctrine_id": metadata.get("doctrine_id", ""),
            # Classificacao juridica
            "posicao_doutrinaria": metadata.get("posicao_doutrinaria", ""),
            "fonte_normativa": metadata.get("fonte_normativa", ""),
            "orgao_julgador": metadata.get("orgao_julgador", ""),
            "artigo_referenciado": metadata.get("artigo_referenciado", ""),
            "peso_normativo": metadata.get("peso_normativo", 0),
        }

        # Limpar valores None
        for k, v in payload.items():
            if v is None:
                payload[k] = ""

        # Adicionar ao batch
        point_id_counter += 1
        batch_points.append(PointStruct(
            id=point_id_counter,
            vector=embedding,
            payload=payload,
        ))

        # Inserir batch
        if len(batch_points) >= BATCH_SIZE:
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=batch_points,
            )
            for p in batch_points:
                migrated_set.add(node_id)
            migrated_count += len(batch_points)
            batch_points = []

            # Salvar progresso
            if migrated_count % 1000 == 0:
                migration_state["migrated_ids"] = list(migrated_set)
                migration_state["total_migrated"] = migrated_count
                with open(MIGRATION_LOG, "w") as f:
                    json.dump(migration_state, f)
                elapsed = time.time() - start_time
                rate = migrated_count / elapsed if elapsed > 0 else 0
                remaining = (total_to_migrate - len(migrated_set)) / rate if rate > 0 else 0
                logger.info(
                    f"  Migrados: {migrated_count}/{total_to_migrate} "
                    f"({rate:.0f}/s, restante: {remaining/60:.0f}min)"
                )

    except Exception as e:
        error_count += 1
        if error_count <= 5:
            logger.error(f"  Erro node {node_id[:20]}: {e}")

# Inserir batch final
if batch_points:
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=batch_points,
    )
    migrated_count += len(batch_points)

# Salvar estado final
migration_state["migrated_ids"] = list(migrated_set)
migration_state["total_migrated"] = migrated_count
with open(MIGRATION_LOG, "w") as f:
    json.dump(migration_state, f)

# ============================================================
# RELATORIO
# ============================================================

elapsed = time.time() - start_time
info = client.get_collection(COLLECTION_NAME)

logger.info("")
logger.info("=" * 60)
logger.info("MIGRACAO CONCLUIDA")
logger.info("=" * 60)
logger.info(f"Nodes migrados: {migrated_count}")
logger.info(f"Nodes pulados (ja migrados): {skipped_count}")
logger.info(f"Erros: {error_count}")
logger.info(f"Total no Qdrant: {info.points_count}")
logger.info(f"Tempo: {elapsed:.0f}s")
logger.info(f"Dados em: {QDRANT_DIR}/")
logger.info("")
logger.info("PROXIMO PASSO:")
logger.info("  Compacte 'qdrant_data/' + 'controle_index.json' em ZIP")
logger.info("  Importe no JuristaAI")
