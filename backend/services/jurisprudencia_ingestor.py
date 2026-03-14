"""Jurisprudência Ingestor — Pipeline profissional de ingestão de jurisprudência brasileira.

Fontes: STJ, STF (repercussão geral)
Indexa APENAS: ementa + tese jurídica (NÃO inteiro teor)
Collection: jurista_jurisprudencia (Qdrant)

Uso no servidor:
    from services.jurisprudencia_ingestor import JurisprudenciaIngestor
    ingestor = JurisprudenciaIngestor()
    ingestor.ingest_from_json(dados)
    ingestor.ingest_from_url(url_stj)
"""

import os
import re
import json
import hashlib
from utils.logger import get_logger
import time
from typing import List, Dict, Optional
from datetime import datetime

logger = get_logger(__name__)

CHUNK_SIZE = 700
CHUNK_OVERLAP = 120
COLLECTION_NAME = "jurista_jurisprudencia"
EMBEDDING_DIM = 384


def _hash(text: str) -> str:
    return hashlib.sha256(text.lower().strip().encode()).hexdigest()[:16]


def _detect_area(texto: str) -> str:
    t = texto.lower()
    areas = {
        "Direito Civil": ["civil", "contrato", "dano", "indenização", "responsabilidade", "família", "alimentos", "locação", "propriedade"],
        "Direito do Consumidor": ["consumidor", "cdc", "fornecedor", "produto", "serviço", "negativação", "cadastro"],
        "Direito Penal": ["penal", "crime", "pena", "roubo", "furto", "tráfico", "prisão", "regime"],
        "Processo Civil": ["recurso", "agravo", "embargos", "competência", "honorários", "execução"],
        "Processo Penal": ["habeas corpus", "prisão preventiva", "inquérito"],
        "Direito Tributário": ["tribut", "icms", "imposto", "contribuição", "fiscal"],
        "Direito Administrativo": ["administrativo", "servidor", "licitação", "improbidade"],
        "Direito do Trabalho": ["trabalh", "clt", "empregado", "rescisão"],
    }
    for area, kws in areas.items():
        if any(k in t for k in kws):
            return area
    return "Geral"


def _extract_keywords(texto: str) -> List[str]:
    """Extrai palavras-chave jurídicas do texto."""
    t = texto.lower()
    all_keywords = [
        "responsabilidade civil", "dano moral", "dano material", "nexo causal",
        "culpa", "dolo", "boa-fé", "má-fé", "prescrição", "decadência",
        "consumidor", "fornecedor", "negativação", "cadastro", "inscrição",
        "contrato", "rescisão", "indenização", "obrigação", "inadimplemento",
        "alimentos", "guarda", "divórcio", "união estável",
        "recurso especial", "agravo", "embargos", "competência",
        "crime", "pena", "prisão", "liberdade", "habeas corpus",
        "tributário", "imposto", "contribuição", "isenção",
        "servidor público", "licitação", "improbidade",
        "in re ipsa", "inversão do ônus", "princípio",
    ]
    found = [kw for kw in all_keywords if kw in t]
    return found[:8]


def _detect_sumula_equivalente(texto: str) -> Optional[str]:
    """Detecta se o texto corresponde a uma súmula existente."""
    match = re.search(r's[uú]mula\s+(?:n[ºo°]?\s*)?(\d+)', texto.lower())
    if match:
        return f"Súmula {match.group(1)}"
    return None


def _detect_repetitivo(texto: str) -> Optional[str]:
    """Detecta tema repetitivo."""
    match = re.search(r'tema\s+(?:n[ºo°]?\s*)?(\d+)', texto.lower())
    if match:
        return f"Tema {match.group(1)}"
    patterns = [
        r'recurso\s+repetitivo', r'repercuss[aã]o\s+geral',
        r'rito\s+dos\s+repetitivos', r'art\.\s*1\.036',
    ]
    for p in patterns:
        if re.search(p, texto.lower()):
            return "repetitivo_detectado"
    return None


def _chunk_text(texto: str) -> List[str]:
    """Chunking jurisprudencial: 700 chars, overlap 120."""
    chunks = []
    if not texto or len(texto.strip()) < 50:
        return chunks

    if len(texto) <= CHUNK_SIZE + 50:
        return [texto.strip()]

    avanco = CHUNK_SIZE - CHUNK_OVERLAP
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + CHUNK_SIZE, len(texto))
        if fim < len(texto):
            for sep in [". ", ".\n", "\n\n", "\n", "; "]:
                pos = texto.rfind(sep, inicio + avanco // 2, fim + 30)
                if pos > inicio + avanco // 2:
                    fim = pos + len(sep)
                    break
        trecho = texto[inicio:fim].strip()
        if len(trecho) >= 50:
            chunks.append(trecho)
        inicio += avanco

    return chunks


class JurisprudenciaIngestor:
    """Pipeline de ingestão de jurisprudência para RAG."""

    def __init__(self):
        self._model = None
        self._client = None
        self._hashes = set()

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        return self._model

    def _get_qdrant(self):
        """Get Qdrant client — remote or local."""
        if self._client is not None:
            return self._client

        qdrant_url = os.environ.get("QDRANT_URL", "")
        if qdrant_url:
            import requests as req
            headers = {"ngrok-skip-browser-warning": "true", "Content-Type": "application/json"}
            # Check if collection exists
            r = req.get(f"{qdrant_url}/collections/{COLLECTION_NAME}", headers=headers, timeout=10)
            if r.status_code == 404 or (r.status_code == 200 and "not found" in r.text.lower()):
                # Create collection
                req.put(f"{qdrant_url}/collections/{COLLECTION_NAME}", json={
                    "vectors": {"size": EMBEDDING_DIM, "distance": "Cosine"}
                }, headers=headers, timeout=10)
                logger.info(f"Collection '{COLLECTION_NAME}' criada no Qdrant remoto")

            self._client = {"type": "rest", "url": qdrant_url, "headers": headers}
            return self._client

        # Local fallback
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import VectorParams, Distance
            path = os.environ.get("QDRANT_LOCAL_PATH", "/app/backend/data/qdrant_juris")
            os.makedirs(path, exist_ok=True)
            client = QdrantClient(path=path)
            collections = [c.name for c in client.get_collections().collections]
            if COLLECTION_NAME not in collections:
                client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )
            self._client = {"type": "local", "client": client}
            return self._client
        except Exception as e:
            logger.error(f"Qdrant init failed: {e}")
            return None

    def _upsert_points(self, points: List[Dict]):
        """Insert points to Qdrant (REST or local)."""
        qdrant = self._get_qdrant()
        if not qdrant:
            return

        if qdrant["type"] == "rest":
            import requests as req
            batch = {"points": [{"id": p["id"], "vector": p["vector"], "payload": p["payload"]} for p in points]}
            r = req.put(
                f"{qdrant['url']}/collections/{COLLECTION_NAME}/points",
                json=batch, headers=qdrant["headers"], timeout=30
            )
            if r.status_code != 200:
                logger.error(f"Qdrant upsert failed: {r.status_code}")
        else:
            from qdrant_client.models import PointStruct
            qdrant["client"].upsert(
                collection_name=COLLECTION_NAME,
                points=[PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in points]
            )

    def ingest_decisao(self, decisao: Dict) -> int:
        """Ingere uma única decisão judicial.

        Args:
            decisao: {tribunal, processo, relator, data_julgamento, tema, ementa, tese, area_direito, palavras_chave}

        Returns:
            Número de chunks indexados
        """
        tribunal = decisao.get("tribunal", "")
        processo = decisao.get("processo", "")
        ementa = decisao.get("ementa", "")
        tese = decisao.get("tese", "")
        area = decisao.get("area_direito", "") or _detect_area(ementa + " " + tese)
        keywords = decisao.get("palavras_chave", []) or _extract_keywords(ementa + " " + tese)

        # Dedup by ementa hash
        ementa_hash = _hash(ementa) if ementa else ""
        if ementa_hash and ementa_hash in self._hashes:
            logger.info(f"  Duplicata: {processo}")
            return 0
        if ementa_hash:
            self._hashes.add(ementa_hash)

        # Detect special types
        sumula_ref = _detect_sumula_equivalente(ementa + " " + tese)
        repetitivo = _detect_repetitivo(ementa + " " + tese)

        # Base metadata
        base_meta = {
            "tipo_documento": "jurisprudencia",
            "source_type": "jurisprudence",
            "tribunal": tribunal,
            "processo": processo,
            "relator": decisao.get("relator", ""),
            "data_julgamento": decisao.get("data_julgamento", ""),
            "tema": decisao.get("tema", ""),
            "area_direito": area,
            "palavras_chave": keywords,
            "ementa_hash": ementa_hash,
            "sumula_equivalente": sumula_ref or "",
            "precedente_repetitivo": repetitivo or "",
            "peso_normativo": 3 if tribunal in ("STF", "STJ") else 2,
        }

        model = self._get_model()
        points = []
        chunk_count = 0

        # Index ementa
        if ementa and len(ementa.strip()) > 50:
            for chunk in _chunk_text(ementa):
                embedding = model.encode(chunk, normalize_embeddings=True)
                chunk_count += 1
                points.append({
                    "id": abs(hash(f"{processo}_ementa_{chunk_count}")) % (2**63),
                    "vector": embedding.tolist(),
                    "payload": {**base_meta, "text": chunk, "secao": "ementa"},
                })

        # Index tese
        if tese and len(tese.strip()) > 30:
            for chunk in _chunk_text(tese):
                embedding = model.encode(chunk, normalize_embeddings=True)
                chunk_count += 1
                points.append({
                    "id": abs(hash(f"{processo}_tese_{chunk_count}")) % (2**63),
                    "vector": embedding.tolist(),
                    "payload": {**base_meta, "text": chunk, "secao": "tese"},
                })

        # Batch insert
        if points:
            self._upsert_points(points)

        return chunk_count

    def ingest_from_json(self, data: List[Dict]) -> Dict:
        """Ingere lista de decisões de um JSON.

        Args:
            data: Lista de dicts com campos obrigatórios

        Returns:
            {total, indexados, duplicatas, erros}
        """
        total = len(data)
        indexados = 0
        duplicatas = 0
        erros = 0

        for i, decisao in enumerate(data):
            try:
                chunks = self.ingest_decisao(decisao)
                if chunks > 0:
                    indexados += 1
                else:
                    duplicatas += 1

                if (i + 1) % 50 == 0:
                    logger.info(f"Progresso: {i+1}/{total} ({indexados} indexados)")

            except Exception as e:
                erros += 1
                logger.error(f"Erro: {e}")

        logger.info(f"Ingestão concluída: {indexados}/{total} indexados, {duplicatas} duplicatas, {erros} erros")
        return {"total": total, "indexados": indexados, "duplicatas": duplicatas, "erros": erros}

    def ingest_from_file(self, path: str) -> Dict:
        """Ingere de arquivo JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("decisoes", data.get("results", [data]))
        return self.ingest_from_json(data)

    def search(self, query: str, n_results: int = 5, tribunal: str = None) -> List[Dict]:
        """Busca jurisprudência."""
        qdrant = self._get_qdrant()
        if not qdrant:
            return []

        model = self._get_model()
        vector = model.encode(query, normalize_embeddings=True).tolist()

        if qdrant["type"] == "rest":
            import requests as req
            payload = {"query": vector, "limit": n_results, "with_payload": True}
            if tribunal:
                payload["filter"] = {"must": [{"key": "tribunal", "match": {"value": tribunal}}]}

            r = req.post(
                f"{qdrant['url']}/collections/{COLLECTION_NAME}/points/query",
                json=payload, headers=qdrant["headers"], timeout=15
            )
            if r.status_code != 200:
                return []

            results = []
            for point in r.json().get("result", {}).get("points", []):
                p = point.get("payload", {})
                results.append({
                    "text": p.get("text", ""),
                    "score": round(point.get("score", 0), 4),
                    "metadata": {k: v for k, v in p.items() if k != "text"},
                })
            return results
        else:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            qf = None
            if tribunal:
                qf = Filter(must=[FieldCondition(key="tribunal", match=MatchValue(value=tribunal))])
            results = qdrant["client"].query_points(
                collection_name=COLLECTION_NAME, query=vector, limit=n_results, query_filter=qf
            )
            return [{
                "text": p.payload.get("text", ""),
                "score": round(p.score, 4),
                "metadata": {k: v for k, v in p.payload.items() if k != "text"},
            } for p in results.points]

    def stats(self) -> Dict:
        """Estatísticas da collection."""
        qdrant = self._get_qdrant()
        if not qdrant:
            return {"total": 0}

        if qdrant["type"] == "rest":
            import requests as req
            r = req.get(f"{qdrant['url']}/collections/{COLLECTION_NAME}", headers=qdrant["headers"], timeout=10)
            if r.status_code == 200:
                return {"total": r.json().get("result", {}).get("points_count", 0)}
        else:
            info = qdrant["client"].get_collection(COLLECTION_NAME)
            return {"total": info.points_count}

        return {"total": 0}
