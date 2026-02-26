"""Crawler de Temas Repetitivos do STJ

Baixa TODOS os 1.411 temas repetitivos do STJ e indexa no Qdrant local.

Uso:
    python crawl_temas_stj.py

Requer:
    pip install requests beautifulsoup4 sentence-transformers qdrant-client
"""

import os
import re
import json
import time
import logging
import hashlib
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("crawl_temas_stj.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("CrawlSTJ")

# ============================================================
# CONFIGURACAO
# ============================================================

QDRANT_DIR = "qdrant_data"
COLLECTION = "jurista_legal_docs"
CHECKPOINT_FILE = "controle_temas_stj.json"
BATCH_SIZE = 50
PER_PAGE = 50
BASE_URL = "https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp"

# ============================================================
# CHECKPOINT
# ============================================================

if os.path.exists(CHECKPOINT_FILE):
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        checkpoint = json.load(f)
else:
    checkpoint = {"paginas_processadas": [], "temas_indexados": [], "total": 0}


def salvar_checkpoint():
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


# ============================================================
# QDRANT
# ============================================================

logger.info("Inicializando Qdrant...")
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

client = QdrantClient(path=QDRANT_DIR)
collections = [c.name for c in client.get_collections().collections]
if COLLECTION not in collections:
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )

try:
    info = client.get_collection(COLLECTION)
    point_id = info.points_count
except Exception:
    point_id = 0

logger.info(f"Qdrant: {point_id} pontos existentes")

# ============================================================
# EMBEDDING MODEL
# ============================================================

logger.info("Carregando modelo de embeddings...")
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
logger.info("Modelo carregado!")

# ============================================================
# PARSER
# ============================================================

def parse_temas_pagina(html: str) -> list:
    """Parseia temas repetitivos de uma pagina HTML do STJ."""
    soup = BeautifulSoup(html, "html.parser")
    temas = []

    # Cada tema esta em um bloco "Documento N"
    # Procurar por "Tema Repetitivo" seguido de numero
    text = soup.get_text()

    # Pattern: Tema Repetitivo\nNNN\n...Tese Firmada\n{texto}
    blocks = re.split(r'Documento \d+', text)

    for block in blocks:
        if "Tema Repetitivo" not in block:
            continue

        # Extrair numero do tema
        tema_match = re.search(r'Tema Repetitivo\s*(\d+)', block)
        if not tema_match:
            continue
        tema_num = int(tema_match.group(1))

        # Extrair tese firmada
        tese = ""
        tese_match = re.search(r'Tese Firmada\s*(.*?)(?=Anota|Delimita|Informa|Repercuss|Entendimento|Refer|$)', block, re.DOTALL)
        if tese_match:
            tese = re.sub(r'\s+', ' ', tese_match.group(1)).strip()

        if not tese or len(tese) < 20:
            continue

        # Extrair area/ramo do direito
        area = "Geral"
        area_match = re.search(r'Ramo do direito\s*(.*?)(?=Quest|$)', block)
        if area_match:
            area = re.sub(r'\s+', ' ', area_match.group(1)).strip()

        # Extrair orgao julgador
        orgao = ""
        orgao_match = re.search(r'[OÓ]rg[aã]o julgador\s*(.*?)(?=Ramo|$)', block)
        if orgao_match:
            orgao = re.sub(r'\s+', ' ', orgao_match.group(1)).strip()

        # Extrair processo
        processo = ""
        proc_match = re.search(r'(REsp|AREsp|EREsp|CC)\s*(\d+/[A-Z]{2})', block)
        if proc_match:
            processo = f"{proc_match.group(1)} {proc_match.group(2)}"

        # Extrair relator
        relator = ""
        rel_match = re.search(r'Relator\s*([A-Z][A-Z\s\.]+?)(?=Embargo|Afeta|$)', block)
        if rel_match:
            relator = rel_match.group(1).strip()[:60]

        # Extrair questao submetida
        questao = ""
        q_match = re.search(r'Quest[aã]o submetida.*?julgamento\s*(.*?)(?=Tese|$)', block, re.DOTALL)
        if q_match:
            questao = re.sub(r'\s+', ' ', q_match.group(1)).strip()

        temas.append({
            "tema": tema_num,
            "tese": tese,
            "questao": questao,
            "area": area,
            "orgao": orgao,
            "processo": processo,
            "relator": relator,
        })

    return temas


def detectar_area(texto):
    t = texto.lower()
    areas = {
        "Direito Civil": ["civil", "contrato", "dano", "indenização", "responsabilidade", "família"],
        "Direito do Consumidor": ["consumidor", "cdc", "fornecedor", "bancário", "financeiro"],
        "Direito Penal": ["penal", "crime", "pena", "execução penal"],
        "Processo Civil": ["processual civil", "recurso", "honorários", "competência"],
        "Direito Tributário": ["tributário", "fiscal", "imposto", "icms"],
        "Direito Administrativo": ["administrativo", "servidor", "licitação"],
        "Direito do Trabalho": ["trabalho", "trabalhista"],
    }
    for area, kws in areas.items():
        if any(k in t for k in kws):
            return area
    return "Geral"


# ============================================================
# CRAWL + INDEX
# ============================================================

total_pages = 29  # 1411 temas / 50 por pagina
total_indexados = 0
batch = []
all_temas = []

logger.info(f"Iniciando crawl de {total_pages} paginas...")
logger.info("=" * 60)

for page in range(total_pages):
    offset = page * PER_PAGE + 1
    page_key = f"page_{page}"

    if page_key in checkpoint.get("paginas_processadas", []):
        logger.info(f"[{page+1}/{total_pages}] Pagina ja processada, pulando...")
        continue

    url = f"{BASE_URL}?novaConsulta=true&tipo_pesquisa=T&situacao=JULGADO&l={PER_PAGE}&i={offset}"
    logger.info(f"[{page+1}/{total_pages}] Baixando offset={offset}...")

    try:
        r = requests.get(url, timeout=30)
        r.encoding = "utf-8"

        if r.status_code != 200:
            logger.error(f"  HTTP {r.status_code}")
            continue

        temas = parse_temas_pagina(r.text)
        logger.info(f"  Temas parseados: {len(temas)}")

        for t in temas:
            tema_key = f"tema_{t['tema']}"
            if tema_key in checkpoint.get("temas_indexados", []):
                continue

            area = t["area"] if t["area"] != "Geral" else detectar_area(t["tese"])

            # Texto para embedding
            texto = f"TEMA REPETITIVO {t['tema']} - STJ\n\nTese firmada: {t['tese']}"
            if t["questao"]:
                texto += f"\n\nQuestão: {t['questao']}"

            emb = model.encode(texto, normalize_embeddings=True)

            point_id += 1
            batch.append(PointStruct(
                id=point_id,
                vector=emb.tolist(),
                payload={
                    "tipo_documento": "jurisprudencia",
                    "source_type": "jurisprudence",
                    "jurisprudence_type": "tema_repetitivo",
                    "tribunal": "STJ",
                    "orgao_julgador": t["orgao"],
                    "processo": t["processo"],
                    "relator": t["relator"],
                    "tema": f"Tema Repetitivo {t['tema']}",
                    "tese": t["tese"],
                    "questao": t["questao"],
                    "area_direito": area,
                    "peso_normativo": 4,
                    "binding_level": "vinculante",
                    "text": texto,
                },
            ))

            checkpoint["temas_indexados"].append(tema_key)
            total_indexados += 1
            all_temas.append(t)

        # Batch insert
        if len(batch) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION, points=batch)
            batch = []
            logger.info(f"  Lote inserido ({total_indexados} total)")

        checkpoint["paginas_processadas"].append(page_key)
        checkpoint["total"] = total_indexados
        salvar_checkpoint()

        # Delay para nao sobrecarregar o STJ
        time.sleep(2)

    except Exception as e:
        logger.error(f"  Erro: {e}")
        time.sleep(5)

# Batch final
if batch:
    client.upsert(collection_name=COLLECTION, points=batch)

# Salvar JSON com todos os temas
with open("temas_repetitivos_stj_completo.json", "w", encoding="utf-8") as f:
    json.dump(all_temas, f, ensure_ascii=False, indent=1)

try:
    client.close()
except Exception:
    pass

salvar_checkpoint()

logger.info("")
logger.info("=" * 60)
logger.info("CRAWL CONCLUIDO")
logger.info("=" * 60)
logger.info(f"Temas indexados: {total_indexados}")
logger.info(f"Salvo em: temas_repetitivos_stj_completo.json")
logger.info(f"Checkpoint: {CHECKPOINT_FILE}")
