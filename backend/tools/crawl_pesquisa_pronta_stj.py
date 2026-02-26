"""Crawler de Pesquisa Pronta do STJ

Baixa TODOS os temas da Pesquisa Pronta do STJ organizados por area do direito.
Cada tema tem link para acórdãos relevantes com ementas.

Uso:
    python crawl_pesquisa_pronta_stj.py

Requer:
    pip install requests beautifulsoup4 sentence-transformers qdrant-client
"""

import os
import re
import json
import time
import logging
import hashlib

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("crawl_pesquisa_pronta.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("CrawlPP")

QDRANT_DIR = "qdrant_data"
COLLECTION = "jurista_legal_docs"
CHECKPOINT = "controle_pesquisa_pronta.json"
BASE_URL = "https://scon.stj.jus.br/SCON/pesquisa_pronta/toc.jsp"

if os.path.exists(CHECKPOINT):
    with open(CHECKPOINT, "r", encoding="utf-8") as f:
        ckpt = json.load(f)
else:
    ckpt = {"temas_processados": [], "total": 0}

def salvar_ckpt():
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, indent=2, ensure_ascii=False)

# Qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer

logger.info("Carregando modelo...")
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

client = QdrantClient(path=QDRANT_DIR)
collections = [c.name for c in client.get_collections().collections]
if COLLECTION not in collections:
    client.create_collection(collection_name=COLLECTION, vectors_config=VectorParams(size=384, distance=Distance.COSINE))

try:
    info = client.get_collection(COLLECTION)
    point_id = info.points_count
except:
    point_id = 0

logger.info(f"Qdrant: {point_id} pontos")

# Areas e seus links da pagina de Pesquisa Pronta
AREAS = {
    "Direito Administrativo": "DIREITO%20ADMINISTRATIVO",
    "Direito Ambiental": "DIREITO%20AMBIENTAL",
    "Direito Civil": "DIREITO%20CIVIL",
    "Direito do Consumidor": "DIREITO%20DO%20CONSUMIDOR",
    "Direito Empresarial": "DIREITO%20EMPRESARIAL",
    "Direito Internacional": "DIREITO%20INTERNACIONAL",
    "Direito Penal": "DIREITO%20PENAL",
    "Direito Previdenciario": "DIREITO%20PREVIDENCI%C1RIO",
    "Processo Civil": "DIREITO%20PROCESSUAL%20CIVIL",
    "Processo Penal": "DIREITO%20PROCESSUAL%20PENAL",
    "Direito Tributario": "DIREITO%20TRIBUT%C1RIO",
}

total_indexados = 0
batch = []

for area_nome, area_code in AREAS.items():
    logger.info(f"\n{'='*50}")
    logger.info(f"AREA: {area_nome}")
    logger.info(f"{'='*50}")

    url = f"{BASE_URL}?livre=%27{area_code}%27.mat."

    try:
        r = requests.get(url, timeout=30)
        r.encoding = "utf-8"
        if r.status_code != 200:
            logger.error(f"  HTTP {r.status_code}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text()

        # Extrair temas da pagina
        # Cada tema aparece como texto descritivo
        # Parsear blocos entre titulos
        lines = text.split("\n")
        current_subtopic = ""
        temas_area = []

        for line in lines:
            line = line.strip()
            if not line or len(line) < 10:
                continue

            # Detectar subtopico (titulo em maiusculas ou negrito)
            if line.isupper() and len(line) < 60:
                current_subtopic = line
                continue

            # Detectar tema (começa com "- " ou é uma descrição longa)
            if line.startswith("- ") or line.startswith("•"):
                tema_texto = line.lstrip("- •").strip()
                if len(tema_texto) > 30:
                    tema_key = hashlib.sha256(tema_texto[:100].encode()).hexdigest()[:12]
                    if tema_key not in ckpt.get("temas_processados", []):
                        temas_area.append({
                            "texto": tema_texto,
                            "subtopico": current_subtopic,
                            "area": area_nome,
                            "key": tema_key,
                        })

        logger.info(f"  Temas novos: {len(temas_area)}")

        for tema in temas_area:
            texto_completo = f"JURISPRUDÊNCIA STJ - {area_nome}\n\n{tema['subtopico']}\n\n{tema['texto']}"

            emb = model.encode(texto_completo, normalize_embeddings=True)
            point_id += 1

            batch.append(PointStruct(
                id=point_id,
                vector=emb.tolist(),
                payload={
                    "tipo_documento": "jurisprudencia",
                    "source_type": "jurisprudence",
                    "jurisprudence_type": "pesquisa_pronta",
                    "tribunal": "STJ",
                    "area_direito": area_nome,
                    "subtopico": tema["subtopico"],
                    "text": texto_completo,
                    "peso_normativo": 3,
                    "binding_level": "persuasive",
                }
            ))

            ckpt["temas_processados"].append(tema["key"])
            total_indexados += 1

        if len(batch) >= 50:
            client.upsert(collection_name=COLLECTION, points=batch)
            batch = []
            ckpt["total"] = total_indexados
            salvar_ckpt()
            logger.info(f"  Lote salvo ({total_indexados} total)")

        time.sleep(2)

    except Exception as e:
        logger.error(f"  Erro: {e}")
        time.sleep(5)

if batch:
    client.upsert(collection_name=COLLECTION, points=batch)

ckpt["total"] = total_indexados
salvar_ckpt()

try:
    client.close()
except:
    pass

logger.info(f"\nCONCLUIDO: {total_indexados} temas indexados")
