"""Indexador de Leis — Vade Mecum + Planalto

Indexa legislacao brasileira artigo por artigo na collection jurista_legal_docs.
Cada artigo = 1 vetor com metadata juridica completa.

Uso:
    python indexar_leis.py
"""

import os
import sys
import json
import hashlib
import re
import time
import logging
from pathlib import Path
from datetime import datetime

try:
    from sentence_transformers import SentenceTransformer
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct
except ImportError as e:
    print(f"Dependencia faltando: {e}")
    print("pip install sentence-transformers qdrant-client")
    sys.exit(1)

# ============================================================
# CONFIGURACAO
# ============================================================

LEGAL_SOURCES_DIR = "legal_sources"
QDRANT_DIR = "qdrant_data"
COLLECTION_NAME = "jurista_legal_docs"
EMBEDDING_DIM = 384
BATCH_SIZE = 200
CHECKPOINT_FILE = "controle_leis.json"

PESOS = {
    "constituicao": 1.0,
    "emenda_constitucional": 0.98,
    "lei_complementar": 0.95,
    "lei_federal": 0.95,
    "decreto": 0.90,
    "resolucao": 0.85,
}

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


# ============================================================
# DETECCAO DE REFERENCIAS NORMATIVAS
# ============================================================

def detectar_referencias_normativas(texto):
    """Detecta artigos de lei referenciados no texto."""
    refs = []
    patterns = [
        r'art\.?\s*(\d+[A-Za-z\-]*)',
        r'\u00a7\s*(\d+)',
        r'inciso\s+([IVXLCDM]+)',
        r'al[ií]nea\s+[\"\']?([a-z])[\"\']?',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, texto, re.IGNORECASE):
            refs.append(match.group(0).strip()[:50])
    return refs[:10]


def detectar_hierarquia(nome_norma, numero_norma):
    """Detecta hierarquia da norma."""
    combined = (nome_norma + " " + numero_norma).lower()
    if "constitui" in combined or "cf" in combined:
        return "constituicao"
    if "lei complementar" in combined:
        return "lei_complementar"
    if "decreto-lei" in combined or "decreto" in combined:
        return "decreto"
    return "lei_federal"


def detectar_area(texto, nome_norma):
    """Detecta area do direito."""
    combined = (nome_norma + " " + texto[:500]).lower()
    areas = {
        "Direito Constitucional": ["constitui", "direitos fundamentais"],
        "Direito Civil": ["c\u00f3digo civil", "obriga\u00e7", "contrato", "pessoa natural"],
        "Direito Penal": ["c\u00f3digo penal", "crime", "pena", "reclusao"],
        "Processo Civil": ["processo civil", "cpc"],
        "Processo Penal": ["processo penal", "cpp", "inqu\u00e9rito"],
        "Direito do Trabalho": ["clt", "trabalho", "empregado"],
        "Direito Tributario": ["tribut", "imposto", "contribui"],
        "Direito do Consumidor": ["consumidor", "cdc", "fornecedor"],
    }
    for area, keywords in areas.items():
        if any(k in combined for k in keywords):
            return area
    return "Geral"


# ============================================================
# MODELO E QDRANT
# ============================================================

logger.info("Carregando modelo de embeddings...")
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
logger.info("Modelo carregado!")

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

# Get next point ID
try:
    info = client.get_collection(COLLECTION_NAME)
    point_id = info.points_count
except Exception:
    point_id = 0

# ============================================================
# PROCESSAR LEIS
# ============================================================

if not os.path.exists(LEGAL_SOURCES_DIR):
    os.makedirs(LEGAL_SOURCES_DIR, exist_ok=True)
    logger.info(f"Pasta criada: {LEGAL_SOURCES_DIR}/")
    logger.info("Coloque JSONs das leis e rode novamente.")
    sys.exit(0)

json_files = sorted(Path(LEGAL_SOURCES_DIR).glob("*.json"))
logger.info(f"Arquivos de lei: {len(json_files)}")

if not json_files:
    logger.info("Nenhum JSON encontrado.")
    sys.exit(0)

start_time = time.time()
total_indexed = 0
batch = []

for json_path in json_files:
    arquivo = json_path.name

    if arquivo in checkpoint.get("leis_processadas", {}):
        logger.info(f"[SKIP] {arquivo}")
        continue

    logger.info(f"[LEI] {arquivo}")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            lei = json.load(f)
    except Exception as e:
        logger.error(f"  Erro: {e}")
        continue

    nome = lei.get("nome_norma", "")
    numero = lei.get("numero", "")
    area_default = lei.get("area", "")
    hierarquia = lei.get("hierarquia", detectar_hierarquia(nome, numero))
    artigos = lei.get("artigos", [])

    if not artigos:
        continue

    logger.info(f"  {nome} ({numero}) - {len(artigos)} artigos")

    artigos_indexados = 0
    for art in artigos:
        artigo_num = str(art.get("artigo", "")).strip()
        texto = str(art.get("texto", "")).strip()
        if not texto or len(texto) < 10 or not artigo_num:
            continue

        texto_embed = f"Art. {artigo_num} do {nome}: {texto}"
        refs = detectar_referencias_normativas(texto)
        area = area_default or detectar_area(texto, nome)
        peso = PESOS.get(hierarquia, 0.90)

        try:
            embedding = model.encode(texto_embed, normalize_embeddings=True)
        except Exception:
            continue

        point_id += 1
        batch.append(PointStruct(
            id=point_id,
            vector=embedding.tolist(),
            payload={
                "tipo_documento": "lei",
                "lei_nome": nome,
                "lei_numero": numero,
                "ano": lei.get("ano", 0),
                "artigo": artigo_num,
                "texto": texto[:2000],
                "area": area,
                "hierarquia": hierarquia,
                "fonte_normativa": "lei_federal",
                "peso_normativo": peso,
                "vigente": lei.get("vigencia", "ativa") == "ativa",
                "fonte": lei.get("fonte", ""),
                "artigos_relacionados": refs,
            }
        ))
        artigos_indexados += 1

        if len(batch) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=batch)
            total_indexed += len(batch)
            batch = []
            logger.info(f"  Indexados: {artigos_indexados}/{len(artigos)}")

    if batch:
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
        total_indexed += len(batch)
        batch = []

    checkpoint["leis_processadas"][arquivo] = {
        "norma": nome, "numero": numero, "artigos": artigos_indexados,
        "indexado_em": datetime.now().isoformat(),
    }
    checkpoint["total_artigos"] = point_id
    salvar_checkpoint()
    logger.info(f"  Concluido: {artigos_indexados} artigos")

try:
    client.close()
except Exception:
    pass

elapsed = time.time() - start_time
logger.info(f"")
logger.info(f"CONCLUIDO: {total_indexed} artigos em {elapsed:.0f}s")
