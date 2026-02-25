"""Indexador de Jurisprudencia — STF, STJ, TRFs, TJs

Indexa decisoes judiciais na collection jurista_legal_docs.
Cada decisao = 1+ vetores (ementa separada do voto).

Uso:
    python indexar_jurisprudencia.py

Entrada:
    data_jurisprudencia/STJ/*.pdf
    data_jurisprudencia/STJ/*.txt
    data_jurisprudencia/STJ/*.json
    data_jurisprudencia/STF/*.pdf
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
    import fitz
except ImportError as e:
    print(f"Dependencia faltando: {e}")
    print("pip install sentence-transformers qdrant-client PyMuPDF")
    sys.exit(1)

try:
    from jurisprudence_extractor import extrair_metadados_decisao, extrair_ementa
except ImportError:
    print("Coloque jurisprudence_extractor.py na mesma pasta.")
    sys.exit(1)

# ============================================================
# CONFIGURACAO
# ============================================================

PASTA_JURISPRUDENCIA = "data_jurisprudencia"
QDRANT_DIR = "qdrant_data"
COLLECTION_NAME = "jurista_legal_docs"
EMBEDDING_DIM = 384
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80
BATCH_SIZE = 200
CHECKPOINT_FILE = "controle_jurisprudencia.json"

PESOS_TRIBUNAL = {
    "STF": 0.92,
    "STJ": 0.90,
    "TST": 0.90,
    "TSE": 0.88,
    "TRF": 0.85, "TRF1": 0.85, "TRF2": 0.85, "TRF3": 0.85, "TRF4": 0.85, "TRF5": 0.85,
    "TJ": 0.85, "TJSP": 0.85, "TJRJ": 0.85, "TJMG": 0.85,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("indexacao_jurisprudencia.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("JurisIndexer")

# Checkpoint
if os.path.exists(CHECKPOINT_FILE):
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        controle = json.load(f)
else:
    controle = {}


def salvar_controle():
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
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


def ler_pdf(path):
    texto = ""
    with fitz.open(path) as doc:
        for page in doc:
            texto += page.get_text()
    return texto


def ler_txt(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def ler_json_decisao(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("texto", data.get("ementa", json.dumps(data, ensure_ascii=False)))


def criar_chunks(texto, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    avanco = chunk_size - overlap
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + chunk_size, len(texto))
        trecho = texto[inicio:fim].strip()
        if len(trecho) >= 40:
            chunks.append(trecho)
        inicio += avanco
    return chunks


def separar_secoes(texto):
    """Separa ementa, voto e dispositivo."""
    ementa, resto = extrair_ementa(texto)
    secoes = {"ementa": ementa, "texto_integral": resto}
    # Detectar voto
    voto_match = re.search(r'(?i)(VOTO|V\s*O\s*T\s*O)(.*?)(?=DISPOSITIVO|ACÓRDÃO|$)', resto, re.DOTALL)
    if voto_match:
        secoes["voto"] = voto_match.group(2).strip()[:5000]
    disp_match = re.search(r'(?i)(DISPOSITIVO|DECISÃO)(.*?)$', resto, re.DOTALL)
    if disp_match:
        secoes["dispositivo"] = disp_match.group(2).strip()[:2000]
    return secoes


# ============================================================
# MODELO E QDRANT
# ============================================================

logger.info("Carregando modelo...")
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

os.makedirs(QDRANT_DIR, exist_ok=True)
client = QdrantClient(path=QDRANT_DIR)

collections = [c.name for c in client.get_collections().collections]
if COLLECTION_NAME not in collections:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )

try:
    info = client.get_collection(COLLECTION_NAME)
    point_id = info.points_count
except Exception:
    point_id = 0

# ============================================================
# PROCESSAR
# ============================================================

if not os.path.exists(PASTA_JURISPRUDENCIA):
    for t in ["STJ", "STF", "TRF", "TJ"]:
        os.makedirs(os.path.join(PASTA_JURISPRUDENCIA, t), exist_ok=True)
    logger.info(f"Pastas criadas em {PASTA_JURISPRUDENCIA}/")
    logger.info("Coloque PDF/TXT/JSON nas pastas e rode novamente.")
    sys.exit(0)

todos = []
for raiz, _, arquivos in os.walk(PASTA_JURISPRUDENCIA):
    for arq in sorted(arquivos):
        ext = arq.lower()
        if ext.endswith((".pdf", ".txt", ".json")):
            todos.append(os.path.join(raiz, arq))

logger.info(f"Decisoes encontradas: {len(todos)}")
if not todos:
    logger.info("Nenhuma decisao.")
    sys.exit(0)

start_time = time.time()
total_chunks = 0
processados = 0
batch = []

for idx, caminho in enumerate(todos):
    arquivo = os.path.basename(caminho)
    pasta_tribunal = os.path.basename(os.path.dirname(caminho))
    file_hash = hash_arquivo(caminho)

    if file_hash in controle:
        continue

    logger.info(f"[{idx+1}/{len(todos)}] {arquivo}")

    try:
        if arquivo.lower().endswith(".pdf"):
            texto = ler_pdf(caminho)
        elif arquivo.lower().endswith(".json"):
            texto = ler_json_decisao(caminho)
        else:
            texto = ler_txt(caminho)

        if len(texto.strip()) < 100:
            continue

        meta = extrair_metadados_decisao(texto, arquivo)
        if meta["tribunal"] == "desconhecido" and pasta_tribunal.upper() in PESOS_TRIBUNAL:
            meta["tribunal"] = pasta_tribunal.upper()

        secoes = separar_secoes(texto)
        peso = PESOS_TRIBUNAL.get(meta["tribunal"], 0.85)

        logger.info(f"  {meta['tribunal']} | {meta['numero_processo']} | {meta['relator']}")

        base_payload = {
            "tipo_documento": "jurisprudencia",
            "tribunal": meta["tribunal"],
            "orgao_julgador": meta["orgao_julgador"],
            "relator": meta["relator"],
            "numero_processo": meta["numero_processo"],
            "classe_processual": meta["classe_processual"],
            "data_julgamento": meta["data_julgamento"],
            "tipo_decisao": meta["tipo_decisao"],
            "fonte_normativa": "jurisprudencia",
            "peso_normativo": peso,
            "arquivo": arquivo,
            "hash": file_hash,
        }

        chunks_decisao = 0

        # Ementa como chunks separados
        if secoes.get("ementa"):
            for chunk in criar_chunks(secoes["ementa"]):
                emb = model.encode(chunk, normalize_embeddings=True)
                point_id += 1
                payload = {**base_payload, "texto": chunk, "secao": "ementa", "is_ementa": True}
                batch.append(PointStruct(id=point_id, vector=emb.tolist(), payload=payload))
                chunks_decisao += 1

        # Texto integral como chunks
        texto_body = secoes.get("voto", "") or secoes.get("texto_integral", texto)
        for chunk in criar_chunks(texto_body):
            emb = model.encode(chunk, normalize_embeddings=True)
            point_id += 1
            payload = {**base_payload, "texto": chunk, "secao": "voto", "is_ementa": False}
            batch.append(PointStruct(id=point_id, vector=emb.tolist(), payload=payload))
            chunks_decisao += 1

        if len(batch) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=batch)
            total_chunks += len(batch)
            batch = []

        processados += 1
        controle[file_hash] = {
            "arquivo": arquivo, "tribunal": meta["tribunal"],
            "processo": meta["numero_processo"], "chunks": chunks_decisao,
            "indexado_em": datetime.now().isoformat(),
        }
        salvar_controle()
        logger.info(f"  Chunks: {chunks_decisao}")

    except Exception as e:
        logger.error(f"  ERRO: {e}")

if batch:
    client.upsert(collection_name=COLLECTION_NAME, points=batch)
    total_chunks += len(batch)

try:
    client.close()
except Exception:
    pass

logger.info(f"")
logger.info(f"CONCLUIDO: {processados} decisoes, {total_chunks} chunks em {time.time()-start_time:.0f}s")
