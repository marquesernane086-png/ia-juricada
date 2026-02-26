"""Migrador SQLite → Qdrant Server

Le os dados do qdrant-client local (SQLite) e envia para Qdrant Server (Docker).

Uso:
    python migrar_para_server.py

Requer Qdrant Server rodando em localhost:6333 (Docker).
"""

import os
import sys
import json
import time
import logging
import sqlite3
import struct

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Migrador")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct
except ImportError:
    print("pip install qdrant-client")
    sys.exit(1)

# ============================================================
# CONFIGURACAO
# ============================================================

SQLITE_PATH = r"qdrant_data\collection\jurista_legal_docs\storage.sqlite"
QDRANT_SERVER = "http://localhost:6333"
COLLECTION_NAME = "jurista_legal_docs"
EMBEDDING_DIM = 384
BATCH_SIZE = 500

if not os.path.exists(SQLITE_PATH):
    print(f"Erro: {SQLITE_PATH} nao encontrado.")
    print("Execute na pasta onde esta a qdrant_data/")
    sys.exit(1)

# ============================================================
# CONECTAR QDRANT SERVER
# ============================================================

logger.info(f"Conectando ao Qdrant Server: {QDRANT_SERVER}")
server = QdrantClient(url=QDRANT_SERVER)

# Criar collection
try:
    server.get_collection(COLLECTION_NAME)
    logger.info(f"Collection existente")
except Exception:
    server.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )
    logger.info(f"Collection '{COLLECTION_NAME}' criada")

info = server.get_collection(COLLECTION_NAME)
existing_points = info.points_count
logger.info(f"Pontos existentes: {existing_points}")

# ============================================================
# LER SQLITE
# ============================================================

logger.info(f"Lendo SQLite: {SQLITE_PATH}")
conn = sqlite3.connect(SQLITE_PATH)

# Descobrir tabelas
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
table_names = [t[0] for t in tables]
logger.info(f"Tabelas: {table_names}")

# Ler pontos
# qdrant-client local armazena em tabelas especificas
# Tentar diferentes formatos

points_data = []

# Tentar formato qdrant-client local
try:
    # Verificar estrutura
    for table in table_names:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        col_names = [c[1] for c in cols]
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if count > 0:
            logger.info(f"  {table}: {count} rows, cols={col_names[:5]}")
except Exception as e:
    logger.error(f"Erro lendo tabelas: {e}")

# Ler vectors e payloads
# O formato do qdrant-client local usa tabelas como:
# points, vectors, payloads, etc.

def try_read_points():
    """Tenta ler pontos de diferentes formatos SQLite do qdrant-client."""
    
    # Formato 1: tabela 'points' com colunas id, vector, payload
    if 'points' in table_names:
        try:
            rows = conn.execute("SELECT * FROM points LIMIT 1").fetchall()
            if rows:
                cols = [d[0] for d in conn.execute("SELECT * FROM points LIMIT 0").description]
                logger.info(f"  Format: points table, cols={cols}")
                return "points_table"
        except Exception:
            pass

    # Formato 2: tabelas separadas vectors + payloads
    if 'vectors' in table_names and 'payloads' in table_names:
        return "separate_tables"

    # Formato 3: tabela com nome da collection
    for t in table_names:
        if 'vector' in t.lower() or 'point' in t.lower():
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                if count > 0:
                    return f"table:{t}"
            except Exception:
                pass

    return None

format_type = try_read_points()
logger.info(f"Formato detectado: {format_type}")

# Ler todos os dados baseado no formato
total_read = 0
batch = []
point_id = existing_points

if format_type == "points_table":
    cursor = conn.execute("SELECT * FROM points")
    cols = [d[0] for d in cursor.description]
    logger.info(f"Colunas: {cols}")
    
    for row in cursor:
        row_dict = dict(zip(cols, row))
        # Extrair vector e payload conforme as colunas
        total_read += 1
        
elif format_type == "separate_tables":
    # Ler vectors
    logger.info("Lendo vectors...")
    vectors = {}
    cursor = conn.execute("SELECT * FROM vectors")
    v_cols = [d[0] for d in cursor.description]
    for row in cursor:
        d = dict(zip(v_cols, row))
        vectors[d.get('id', d.get('point_id', total_read))] = d
    logger.info(f"  Vectors: {len(vectors)}")
    
    # Ler payloads
    logger.info("Lendo payloads...")
    payloads = {}
    cursor = conn.execute("SELECT * FROM payloads")
    p_cols = [d[0] for d in cursor.description]
    for row in cursor:
        d = dict(zip(p_cols, row))
        payloads[d.get('id', d.get('point_id', total_read))] = d
    logger.info(f"  Payloads: {len(payloads)}")

else:
    # Formato desconhecido - dump todas as tabelas para diagnostico
    logger.info("Formato desconhecido. Dumping tabelas para diagnostico...")
    for table in table_names:
        try:
            cursor = conn.execute(f"SELECT * FROM [{table}] LIMIT 3")
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            logger.info(f"\n  TABLE: {table}")
            logger.info(f"  COLS: {cols}")
            for row in rows:
                # Show first 100 chars of each value
                vals = [str(v)[:100] if v else "NULL" for v in row]
                logger.info(f"  ROW: {vals}")
        except Exception as e:
            logger.info(f"  TABLE {table}: error {e}")

conn.close()
logger.info(f"\nTotal lido: {total_read}")
logger.info("Script de diagnostico concluido.")
logger.info("Envie o output para o desenvolvedor para ajustar a migracao.")
