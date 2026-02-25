"""JurisprudenceAI — Indexador de Jurisprudência

Subsistema independente do DoctrineAI.
Indexa decisões judiciais em collection Qdrant separada.

Uso:
    python indexar_jurisprudencia.py

Estrutura esperada:
    data_jurisprudencia/
        STJ/
            decisao1.pdf
            decisao2.txt
        STF/
            decisao3.pdf
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
    import fitz
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct
    from sentence_transformers import SentenceTransformer
    from jurisprudence_extractor import extrair_metadados_decisao, extrair_ementa
except ImportError as e:
    print(f"Dependencia faltando: {e}")
    print("pip install PyMuPDF qdrant-client sentence-transformers")
    sys.exit(1)

# ============================================================
# CONFIGURACAO
# ============================================================

PASTA_JURISPRUDENCIA = "data_jurisprudencia"
QDRANT_DIR = "qdrant_data"
COLLECTION_NAME = "jurista_jurisprudencia"
EMBEDDING_DIM = 384
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80
ARQUIVO_CONTROLE = "controle_jurisprudencia.json"
BATCH_SIZE = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("indexacao_jurisprudencia.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("JurisprudenceAI")

# Modelo de embeddings (mesmo da doutrina)
logger.info("Carregando modelo de embeddings...")
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
logger.info("Modelo carregado!")

# Controle
if os.path.exists(ARQUIVO_CONTROLE):
    with open(ARQUIVO_CONTROLE, "r", encoding="utf-8") as f:
        controle = json.load(f)
else:
    controle = {}


def salvar_controle():
    with open(ARQUIVO_CONTROLE, "w", encoding="utf-8") as f:
        json.dump(controle, f, indent=2, ensure_ascii=False)


def hash_arquivo(path):
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            bloco = f.read(8192)
            if not bloco:
                break
            sha.update(bloco)
    return sha.hexdigest()


# ============================================================
# LEITURA
# ============================================================

def ler_pdf(path):
    texto = ""
    with fitz.open(path) as doc:
        for page in doc:
            texto += page.get_text()
    return texto


def ler_txt(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


# ============================================================
# CHUNKING JURISPRUDENCIAL (400 chars, corte em paragrafo)
# ============================================================

def criar_chunks_jurisprudencia(texto, metadata_base, is_ementa=False):
    """Chunks especializados para jurisprudencia."""
    chunks = []

    if len(texto.strip()) < 50:
        return chunks

    avanco = CHUNK_SIZE - CHUNK_OVERLAP

    if len(texto) <= CHUNK_SIZE + 50:
        meta = {**metadata_base, "is_ementa": is_ementa}
        embedding = model.encode(texto.strip(), normalize_embeddings=True)
        chunks.append({"text": texto.strip(), "metadata": meta, "embedding": embedding.tolist()})
        return chunks

    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + CHUNK_SIZE, len(texto))

        # Cortar em paragrafo ou ponto
        if fim < len(texto):
            for sep in ["\n\n", "\n", ". ", "; "]:
                pos = texto.rfind(sep, inicio + avanco // 2, fim + 30)
                if pos > inicio + avanco // 2:
                    fim = pos + len(sep)
                    break

        trecho = texto[inicio:fim].strip()
        if len(trecho) >= 40:
            meta = {**metadata_base, "is_ementa": is_ementa}
            embedding = model.encode(trecho, normalize_embeddings=True)
            chunks.append({"text": trecho, "metadata": meta, "embedding": embedding.tolist()})

        inicio += avanco

    return chunks


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
    logger.info(f"Collection existente: {info.points_count} pontos")


# ============================================================
# PROCESSAMENTO
# ============================================================

if not os.path.exists(PASTA_JURISPRUDENCIA):
    os.makedirs(os.path.join(PASTA_JURISPRUDENCIA, "STJ"), exist_ok=True)
    os.makedirs(os.path.join(PASTA_JURISPRUDENCIA, "STF"), exist_ok=True)
    logger.info(f"Pasta criada: {PASTA_JURISPRUDENCIA}/STJ e /STF")
    logger.info("Coloque os arquivos PDF/TXT nas pastas e rode novamente.")
    sys.exit(0)

# Encontrar arquivos
todos = []
for raiz, _, arquivos in os.walk(PASTA_JURISPRUDENCIA):
    for arq in sorted(arquivos):
        ext = arq.lower()
        if ext.endswith(".pdf") or ext.endswith(".txt"):
            todos.append(os.path.join(raiz, arq))

logger.info(f"Decisoes encontradas: {len(todos)}")
if not todos:
    logger.info("Nenhuma decisao encontrada.")
    sys.exit(0)

start_time = time.time()
total_chunks = 0
processados = 0
pulados = 0
erros = 0
point_id = 0
batch = []

# Pegar ultimo point_id do Qdrant
try:
    info = client.get_collection(COLLECTION_NAME)
    point_id = info.points_count
except Exception:
    pass

for idx, caminho in enumerate(todos):
    arquivo = os.path.basename(caminho)
    pasta_tribunal = os.path.basename(os.path.dirname(caminho))
    file_hash = hash_arquivo(caminho)

    if file_hash in controle:
        pulados += 1
        continue

    logger.info(f"[{idx+1}/{len(todos)}] {arquivo}")

    try:
        # Ler
        if arquivo.lower().endswith(".pdf"):
            texto = ler_pdf(caminho)
        else:
            texto = ler_txt(caminho)

        if len(texto.strip()) < 100:
            logger.warning("  Texto insuficiente")
            erros += 1
            continue

        # Extrair metadados
        meta = extrair_metadados_decisao(texto, arquivo)

        # Se tribunal nao detectado, usar nome da pasta
        if meta["tribunal"] == "desconhecido" and pasta_tribunal.upper() in ["STJ", "STF", "TST", "TRF"]:
            meta["tribunal"] = pasta_tribunal.upper()

        logger.info(f"  Tribunal: {meta['tribunal']} | Processo: {meta['numero_processo']} | Relator: {meta['relator']}")

        # Separar ementa
        ementa, texto_sem_ementa = extrair_ementa(texto)

        metadata_base = {
            "source_type": "jurisprudencia",
            "tribunal": meta["tribunal"],
            "processo": meta["numero_processo"],
            "classe": meta["classe_processual"],
            "relator": meta["relator"],
            "data_julgamento": meta["data_julgamento"],
            "orgao_julgador": meta["orgao_julgador"],
            "tipo_decisao": meta["tipo_decisao"],
            "peso_normativo": 3,
            "hierarquia": "precedente",
            "arquivo": arquivo,
            "hash": file_hash,
        }

        # Chunks da ementa (separados)
        chunks_ementa = []
        if ementa:
            chunks_ementa = criar_chunks_jurisprudencia(ementa, metadata_base, is_ementa=True)

        # Chunks do texto integral
        chunks_texto = criar_chunks_jurisprudencia(texto_sem_ementa, metadata_base, is_ementa=False)

        all_chunks = chunks_ementa + chunks_texto
        total_chunks += len(all_chunks)

        # Inserir no Qdrant
        for chunk in all_chunks:
            point_id += 1
            payload = {**chunk["metadata"], "text": chunk["text"]}
            for k, v in payload.items():
                if v is None:
                    payload[k] = ""
            batch.append(PointStruct(id=point_id, vector=chunk["embedding"], payload=payload))

        if len(batch) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=batch)
            batch = []

        processados += 1

        controle[file_hash] = {
            "arquivo": arquivo,
            "tribunal": meta["tribunal"],
            "processo": meta["numero_processo"],
            "chunks": len(all_chunks),
            "indexado_em": datetime.now().isoformat(),
        }
        salvar_controle()

        logger.info(f"  Chunks: {len(all_chunks)} (ementa: {len(chunks_ementa)}, texto: {len(chunks_texto)})")

    except Exception as e:
        erros += 1
        logger.error(f"  ERRO: {e}")

# Batch final
if batch:
    client.upsert(collection_name=COLLECTION_NAME, points=batch)

try:
    client.close()
except Exception:
    pass

elapsed = time.time() - start_time

logger.info("")
logger.info("=" * 60)
logger.info("INDEXACAO JURISPRUDENCIA CONCLUIDA")
logger.info("=" * 60)
logger.info(f"Decisoes processadas: {processados}")
logger.info(f"Puladas (ja indexadas): {pulados}")
logger.info(f"Erros: {erros}")
logger.info(f"Total chunks: {total_chunks}")
logger.info(f"Tempo: {elapsed:.0f}s")
logger.info(f"Collection: {COLLECTION_NAME}")
