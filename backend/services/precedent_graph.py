"""Precedent Graph Engine — Grafo de Precedentes Jurídicos

Camada semântica acima da jurisprudência vetorial.
Transforma decisões em GRAFO conectando:
- decisões, teses, artigos de lei, tribunais

NÃO substitui Qdrant. Complementa:
  Vector Search → encontra textos
  Graph Engine  → entende relações jurídicas

Armazenamento: JSON simples (nodes.json + edges.json)
Preparado para escala (milhões de decisões).
"""

import os
import json
import hashlib
import re
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

GRAPH_DIR = str(Path(__file__).parent.parent / "data" / "precedent_graph")

# ============================================================
# NODE TYPES
# ============================================================

NODE_TYPES = {
    "decision": "DECISION_NODE",
    "thesis": "THESIS_NODE",
    "article": "LEGAL_ARTICLE_NODE",
    "court": "COURT_NODE",
}

# ============================================================
# EDGE TYPES
# ============================================================

EDGE_TYPES = {
    "cita": "CITA",                    # DECISION → DECISION
    "fundamenta": "FUNDAMENTA",        # DECISION → THESIS
    "baseada_em": "BASEADA_EM",        # THESIS → ARTICLE
    "julgado_por": "JULGADO_POR",      # DECISION → COURT
    "diverge_de": "DIVERGE_DE",        # THESIS → THESIS
    "confirma": "CONFIRMA",            # DECISION → DECISION
    "supera": "SUPERA",                # DECISION → DECISION (overrule)
}

# ============================================================
# COURT WEIGHTS
# ============================================================

COURT_WEIGHTS = {
    "STF": 3.0,
    "STJ": 2.5,
    "TST": 2.5,
    "TSE": 2.5,
    "STM": 2.5,
    "TRF": 2.0,
    "TRF1": 2.0, "TRF2": 2.0, "TRF3": 2.0, "TRF4": 2.0, "TRF5": 2.0,
    "TJ": 2.0,
    "TJSP": 2.0, "TJRJ": 2.0, "TJMG": 2.0, "TJRS": 2.0,
}

# ============================================================
# ID GENERATION
# ============================================================

def _hash(text: str) -> str:
    return hashlib.sha256(text.lower().strip().encode("utf-8")).hexdigest()[:16]


def decision_id(numero_processo: str, tribunal: str) -> str:
    return f"dec_{_hash(f'{numero_processo}|{tribunal}')}"


def thesis_id(texto_tese: str) -> str:
    normalized = re.sub(r'\s+', ' ', texto_tese.lower().strip())
    return f"tese_{_hash(normalized)}"


def article_id(numero_artigo: str, lei: str = "") -> str:
    return f"art_{numero_artigo}_{_hash(lei)}" if lei else f"art_{numero_artigo}"


def court_id(tribunal: str) -> str:
    return f"court_{tribunal.lower()}"


# ============================================================
# GRAPH STORAGE
# ============================================================

class PrecedentGraph:
    """Grafo de precedentes jurídicos em JSON."""

    def __init__(self, graph_dir: str = GRAPH_DIR):
        self.graph_dir = graph_dir
        self.nodes_path = os.path.join(graph_dir, "nodes.json")
        self.edges_path = os.path.join(graph_dir, "edges.json")
        self.nodes: Dict[str, Dict] = {}
        self.edges: List[Dict] = []
        self._load()

    def _load(self):
        os.makedirs(self.graph_dir, exist_ok=True)
        if os.path.exists(self.nodes_path):
            with open(self.nodes_path, "r", encoding="utf-8") as f:
                self.nodes = json.load(f)
        if os.path.exists(self.edges_path):
            with open(self.edges_path, "r", encoding="utf-8") as f:
                self.edges = json.load(f)
        logger.info(f"Graph loaded: {len(self.nodes)} nodes, {len(self.edges)} edges")

    def save(self):
        with open(self.nodes_path, "w", encoding="utf-8") as f:
            json.dump(self.nodes, f, ensure_ascii=False, indent=1)
        with open(self.edges_path, "w", encoding="utf-8") as f:
            json.dump(self.edges, f, ensure_ascii=False, indent=1)

    # ---- NODES ----

    def add_decision(self, processo: str, tribunal: str, metadata: Dict = None) -> str:
        nid = decision_id(processo, tribunal)
        if nid not in self.nodes:
            self.nodes[nid] = {
                "id": nid,
                "type": NODE_TYPES["decision"],
                "processo": processo,
                "tribunal": tribunal,
                "weight": COURT_WEIGHTS.get(tribunal, 1.0),
                "metadata": metadata or {},
                "created": datetime.now().isoformat(),
            }
        return nid

    def add_thesis(self, texto_tese: str, legal_area: str = "", position: str = "") -> str:
        nid = thesis_id(texto_tese)
        if nid not in self.nodes:
            self.nodes[nid] = {
                "id": nid,
                "type": NODE_TYPES["thesis"],
                "text": texto_tese[:500],
                "legal_area": legal_area,
                "position": position,  # favoravel, restritiva, ampliativa
                "confidence": 0.0,
                "support_count": 0,
                "created": datetime.now().isoformat(),
            }
        # Increment support count
        self.nodes[nid]["support_count"] = self.nodes[nid].get("support_count", 0) + 1
        return nid

    def add_article(self, numero: str, lei: str = "") -> str:
        nid = article_id(numero, lei)
        if nid not in self.nodes:
            self.nodes[nid] = {
                "id": nid,
                "type": NODE_TYPES["article"],
                "numero": numero,
                "lei": lei,
                "citation_count": 0,
                "created": datetime.now().isoformat(),
            }
        self.nodes[nid]["citation_count"] = self.nodes[nid].get("citation_count", 0) + 1
        return nid

    def add_court(self, tribunal: str) -> str:
        nid = court_id(tribunal)
        if nid not in self.nodes:
            self.nodes[nid] = {
                "id": nid,
                "type": NODE_TYPES["court"],
                "tribunal": tribunal,
                "weight": COURT_WEIGHTS.get(tribunal, 1.0),
                "decision_count": 0,
            }
        self.nodes[nid]["decision_count"] = self.nodes[nid].get("decision_count", 0) + 1
        return nid

    # ---- EDGES ----

    def add_edge(self, source: str, target: str, edge_type: str, metadata: Dict = None):
        # Avoid duplicate edges
        for e in self.edges:
            if e["source"] == source and e["target"] == target and e["type"] == edge_type:
                return
        self.edges.append({
            "source": source,
            "target": target,
            "type": edge_type,
            "metadata": metadata or {},
            "created": datetime.now().isoformat(),
        })

    # ---- QUERIES ----

    def get_node(self, node_id: str) -> Optional[Dict]:
        return self.nodes.get(node_id)

    def get_edges_from(self, node_id: str, edge_type: str = None) -> List[Dict]:
        return [
            e for e in self.edges
            if e["source"] == node_id and (edge_type is None or e["type"] == edge_type)
        ]

    def get_edges_to(self, node_id: str, edge_type: str = None) -> List[Dict]:
        return [
            e for e in self.edges
            if e["target"] == node_id and (edge_type is None or e["type"] == edge_type)
        ]

    def get_theses_for_topic(self, legal_area: str) -> List[Dict]:
        return [
            n for n in self.nodes.values()
            if n["type"] == NODE_TYPES["thesis"] and legal_area.lower() in n.get("legal_area", "").lower()
        ]

    def get_dominant_thesis(self, legal_area: str) -> Optional[Dict]:
        theses = self.get_theses_for_topic(legal_area)
        if not theses:
            return None
        return max(theses, key=lambda t: t.get("support_count", 0))

    def find_divergences(self, legal_area: str) -> List[Dict]:
        return [
            e for e in self.edges
            if e["type"] == EDGE_TYPES["diverge_de"]
            and self.nodes.get(e["source"], {}).get("legal_area", "").lower() == legal_area.lower()
        ]

    def get_leading_cases(self, tribunal: str = None, limit: int = 10) -> List[Dict]:
        decisions = [
            n for n in self.nodes.values()
            if n["type"] == NODE_TYPES["decision"]
            and (tribunal is None or n.get("tribunal") == tribunal)
        ]
        # Sort by weight * number of outgoing FUNDAMENTA edges
        for d in decisions:
            cites = len(self.get_edges_from(d["id"], EDGE_TYPES["fundamenta"]))
            d["_relevance"] = d.get("weight", 1.0) * (1 + cites)
        decisions.sort(key=lambda x: x.get("_relevance", 0), reverse=True)
        return decisions[:limit]

    def stats(self) -> Dict:
        type_counts = {}
        for n in self.nodes.values():
            t = n.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        edge_counts = {}
        for e in self.edges:
            t = e.get("type", "unknown")
            edge_counts[t] = edge_counts.get(t, 0) + 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": type_counts,
            "edge_types": edge_counts,
        }


# ============================================================
# DECISION PROCESSOR (popula o grafo)
# ============================================================

def process_decision(graph: PrecedentGraph, decision_meta: Dict, texto: str):
    """Processa uma decisão e adiciona ao grafo.

    Args:
        graph: Instância do PrecedentGraph
        decision_meta: Metadados extraídos (tribunal, processo, etc.)
        texto: Texto integral da decisão
    """
    tribunal = decision_meta.get("tribunal", "desconhecido")
    processo = decision_meta.get("numero_processo", "desconhecido")

    # Node: decisão
    dec_id = graph.add_decision(processo, tribunal, decision_meta)

    # Node: tribunal
    ct_id = graph.add_court(tribunal)
    graph.add_edge(dec_id, ct_id, EDGE_TYPES["julgado_por"])

    # Extrair artigos citados
    artigos = _extrair_artigos(texto)
    for art_num, lei in artigos:
        art_id = graph.add_article(art_num, lei)
        graph.add_edge(dec_id, art_id, EDGE_TYPES["baseada_em"])

    # Extrair tese (heurística — sem LLM)
    tese = _extrair_tese_heuristica(texto)
    if tese:
        area = decision_meta.get("classe_processual", "")
        t_id = graph.add_thesis(tese, legal_area=area)
        graph.add_edge(dec_id, t_id, EDGE_TYPES["fundamenta"])

    # Detectar citações a outras decisões
    decisoes_citadas = _extrair_decisoes_citadas(texto)
    for proc_citado, trib_citado in decisoes_citadas:
        cited_id = graph.add_decision(proc_citado, trib_citado)
        graph.add_edge(dec_id, cited_id, EDGE_TYPES["cita"])


def _extrair_artigos(texto: str) -> List[tuple]:
    """Extrai artigos de lei citados."""
    artigos = []
    # art. 927 do CC, art. 5º da CF, art. 186 do Código Civil
    pattern = r'art\.?\s*(\d+[A-Za-z\-]*)\s*(?:do|da|,)\s*((?:C[oó]digo Civil|CC|CF|CPC|CDC|CP\b|CLT|Constitui[cç][aã]o)[^\n,]{0,30})'
    for match in re.finditer(pattern, texto, re.IGNORECASE):
        artigos.append((match.group(1), match.group(2).strip()[:40]))
    return artigos[:20]  # max 20


def _extrair_tese_heuristica(texto: str) -> str:
    """Extrai tese principal por heurística (sem LLM)."""
    # Procurar padrões de tese
    patterns = [
        r'(?:tese\s*(?:firmada|fixada)[:\s]*)(.*?)(?:\.|$)',
        r'(?:entendimento\s*(?:de que|no sentido)[:\s]*)(.*?)(?:\.|$)',
        r'(?:fixou[\-\s]*se\s*(?:a tese|o entendimento)[:\s]*)(.*?)(?:\.|$)',
    ]
    for pattern in patterns:
        match = re.search(pattern, texto[:5000], re.IGNORECASE)
        if match and len(match.group(1).strip()) > 20:
            return match.group(1).strip()[:500]
    return ""


def _extrair_decisoes_citadas(texto: str) -> List[tuple]:
    """Extrai referências a outras decisões."""
    citadas = []
    # REsp 1234567/SP, RE 567890, HC 12345
    pattern = r'(REsp|RE|HC|MS|AgRg|AgInt|AREsp)\s*n?[ºo°]?\s*([\d\.]+(?:/[A-Z]{2})?)'
    for match in re.finditer(pattern, texto[:10000]):
        classe = match.group(1)
        numero = match.group(2)
        # Inferir tribunal pela classe
        trib = "STJ" if classe in ["REsp", "AgRg", "AgInt", "AREsp"] else "STF" if classe == "RE" else "desconhecido"
        citadas.append((f"{classe} {numero}", trib))
    return citadas[:30]  # max 30


# ============================================================
# SINGLETON
# ============================================================

_graph_instance = None


def get_graph() -> PrecedentGraph:
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = PrecedentGraph()
    return _graph_instance
