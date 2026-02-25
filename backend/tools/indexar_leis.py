"""Indexador de Leis — Pipeline dedicado a legislação brasileira

Collection Qdrant separada: jurista_leis
Cada ARTIGO = 1 vetor (nao chunka como livro)

Uso:
    python indexar_leis.py

Estrutura de entrada (legal_sources/*.json):
{
  "nome_norma": "Código Civil",
  "numero": "Lei 10.406/2002",
  "area": "Direito Civil",
  "artigos": [
    {"artigo": "186", "texto": "..."}
  ]
}
"""

import os
import sys
import json
import hashlib
import logging
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("indexacao_leis.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("LeiIndexer")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    print(f"Dependencia faltando: {e}")
    print("pip install qdrant-client sentence-transformers")
    sys.exit(1)

# ============================================================
# CONFIGURACAO
# ============================================================

LEGAL_SOURCES_DIR = "legal_sources"
QDRANT_DIR = "qdrant_data"
COLLECTION_NAME = "jurista_leis"
EMBEDDING_DIM = 384
BATCH_SIZE = 500
CHECKPOINT_FILE = "controle_leis.json"

# ============================================================
# CHECKPOINT
# ============================================================

if os.path.exists(CHECKPOINT_FILE):
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        checkpoint = json.load(f)
else:
    checkpoint = {"leis_processadas": {}, "total_artigos": 0}


def salvar_checkpoint():
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


def art_hash(norma: str, artigo: str) -> str:
    return hashlib.sha256(f"{norma}|{artigo}".lower().encode()).hexdigest()[:16]


# ============================================================
# EMBEDDING MODEL
# ============================================================

logger.info("Carregando modelo de embeddings...")
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
logger.info("Modelo carregado!")

# ============================================================
# QDRANT
# ============================================================

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
    logger.info(f"Collection existente: {info.points_count} artigos")

# ============================================================
# PROCESSAR LEIS
# ============================================================

if not os.path.exists(LEGAL_SOURCES_DIR):
    os.makedirs(LEGAL_SOURCES_DIR, exist_ok=True)
    logger.info(f"Pasta criada: {LEGAL_SOURCES_DIR}/")
    logger.info("Coloque arquivos JSON das leis e rode novamente.")
    logger.info("Veja legal_sources/codigo_civil.json como exemplo.")
    sys.exit(0)

# Encontrar JSONs
json_files = sorted(Path(LEGAL_SOURCES_DIR).glob("*.json"))
logger.info(f"Arquivos de lei encontrados: {len(json_files)}")

if not json_files:
    logger.info("Nenhum JSON encontrado em legal_sources/")
    sys.exit(0)

start_time = time.time()
total_indexed = 0
total_skipped = 0
total_errors = 0
point_id = checkpoint.get("total_artigos", 0)
batch = []

for json_path in json_files:
    arquivo = json_path.name
    
    # Verificar checkpoint
    if arquivo in checkpoint.get("leis_processadas", {}):
        total_skipped += checkpoint["leis_processadas"][arquivo].get("artigos", 0)
        logger.info(f"[SKIP] {arquivo} (ja indexado)")
        continue

    logger.info(f"[LEI] {arquivo}")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            lei = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"  JSON invalido: {e}")
        total_errors += 1
        continue
    except Exception as e:
        logger.error(f"  Erro lendo: {e}")
        total_errors += 1
        continue

    nome_norma = lei.get("nome_norma", "")
    numero = lei.get("numero", "")
    area = lei.get("area", "")
    hierarquia = lei.get("hierarquia", "lei_federal")
    vigencia = lei.get("vigencia", "ativa")
    fonte = lei.get("fonte", "")
    artigos = lei.get("artigos", [])

    if not artigos:
        logger.warning("  Sem artigos")
        continue

    logger.info(f"  Norma: {nome_norma} ({numero})")
    logger.info(f"  Artigos encontrados: {len(artigos)}")

    artigos_indexados = 0

    for art in artigos:
        artigo_num = str(art.get("artigo", "")).strip()
        texto = str(art.get("texto", "")).strip()

        if not texto or len(texto) < 10:
            continue

        if not artigo_num:
            continue

        # Texto para embedding: inclui contexto da norma
        texto_embedding = f"Art. {artigo_num} do {nome_norma}: {texto}"

        try:
            embedding = model.encode(texto_embedding, normalize_embeddings=True)
        except Exception as e:
            logger.error(f"  Erro embedding art. {artigo_num}: {e}")
            total_errors += 1
            continue

        # Hierarquia peso
        pesos = {
            "constituicao": 5,
            "emenda_constitucional": 4,
            "lei_complementar": 3,
            "lei_federal": 3,
            "decreto": 2,
            "resolucao": 1,
        }

        point_id += 1
        payload = {
            "tipo": "lei",
            "norma": nome_norma,
            "numero_norma": numero,
            "artigo": artigo_num,
            "texto": texto,
            "texto_embedding": texto_embedding,
            "area": area,
            "hierarquia": hierarquia,
            "vigencia": vigencia,
            "fonte": fonte,
            "peso_normativo": pesos.get(hierarquia, 2),
            "art_hash": art_hash(numero, artigo_num),
        }

        batch.append(PointStruct(
            id=point_id,
            vector=embedding.tolist(),
            payload=payload,
        ))

        artigos_indexados += 1

        # Batch insert
        if len(batch) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=batch)
            total_indexed += len(batch)
            batch = []
            logger.info(f"  Inseridos: {artigos_indexados}/{len(artigos)}")

    # Insert remaining
    if batch:
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
        total_indexed += len(batch)
        batch = []

    # Checkpoint
    checkpoint["leis_processadas"][arquivo] = {
        "norma": nome_norma,
        "numero": numero,
        "artigos": artigos_indexados,
        "indexado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    checkpoint["total_artigos"] = point_id
    salvar_checkpoint()

    logger.info(f"  Indexados: {artigos_indexados} artigos")
    logger.info("  Checkpoint salvo")

# ============================================================
# FINALIZAR
# ============================================================

try:
    client.close()
except Exception:
    pass

elapsed = time.time() - start_time
logger.info("")
logger.info("=" * 60)
logger.info("INDEXACAO DE LEIS CONCLUIDA")
logger.info("=" * 60)
logger.info(f"Artigos indexados: {total_indexed}")
logger.info(f"Artigos pulados (checkpoint): {total_skipped}")
logger.info(f"Erros: {total_errors}")
logger.info(f"Tempo: {elapsed:.0f}s")
logger.info(f"Collection: {COLLECTION_NAME}")
logger.info("")
logger.info("Para adicionar mais leis:")
logger.info("  1. Crie um JSON em legal_sources/ seguindo o formato")
logger.info("  2. Rode novamente: python indexar_leis.py")
