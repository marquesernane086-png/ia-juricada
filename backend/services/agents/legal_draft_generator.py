"""Legal Draft Generator — Geração de Peças

📝 PREPARATION MODE — NOT CONNECTED TO RUNTIME

Generates structured legal document blueprints (NOT full petitions).
Produces a drafting plan with logical structure, required arguments,
and doctrinal foundations.

IMPORTANT:
- NEVER generates full petitions automatically
- Only produces drafting blueprint/outline
- Requires human review before any use
"""

ENABLED = False

from typing import Dict, List, Optional
from pydantic import BaseModel


# ============================================================
# SCHEMAS
# ============================================================

class ArgumentBlock(BaseModel):
    """A logical argument block for the petition."""
    position: int  # order in the document
    section: str  # preliminar, mérito, pedido
    argument_title: str
    legal_basis: List[str] = []  # artigos de lei
    doctrinal_support: List[str] = []  # autores/obras
    key_points: List[str] = []
    counter_arguments: List[str] = []  # possíveis contra-argumentos


class DraftBlueprint(BaseModel):
    """Output: structured drafting blueprint."""
    document_type: str  # petição inicial, contestação, apelação, etc.
    competence: str  # juízo competente
    parties: Dict[str, str] = {}  # autor, réu, etc.
    facts_summary: str
    preliminaries: List[ArgumentBlock] = []
    merits: List[ArgumentBlock] = []
    requests: List[str] = []
    estimated_pages: int = 0
    urgency: str = ""  # normal, urgente (tutela provisória)
    observations: List[str] = []


# ============================================================
# DOCUMENT TYPES
# ============================================================

DOCUMENT_STRUCTURES = {
    "petição inicial": {
        "sections": ["endereçamento", "qualificação", "fatos", "direito", "pedidos", "valor da causa"],
        "cpc_basis": "Art. 319, CPC",
    },
    "contestação": {
        "sections": ["preliminares", "mérito", "pedidos"],
        "cpc_basis": "Art. 335 e ss., CPC",
    },
    "apelação": {
        "sections": ["cabimento", "tempestividade", "razões", "pedido de reforma"],
        "cpc_basis": "Art. 1.009 e ss., CPC",
    },
    "agravo de instrumento": {
        "sections": ["cabimento", "hipótese art. 1.015", "razões", "pedido liminar"],
        "cpc_basis": "Art. 1.015 e ss., CPC",
    },
    "embargos de declaração": {
        "sections": ["cabimento", "vício identificado", "esclarecimento pretendido"],
        "cpc_basis": "Art. 1.022, CPC",
    },
    "recurso especial": {
        "sections": ["cabimento", "prequestionamento", "violação legal", "pedido"],
        "cpc_basis": "Art. 1.029, CPC",
    },
    "habeas corpus": {
        "sections": ["autoridade coatora", "constrangimento ilegal", "fundamentação", "pedido liminar"],
        "legal_basis": "Art. 5º, LXVIII, CF; Art. 647 e ss., CPP",
    },
}


# ============================================================
# CORE LOGIC (skeleton)
# ============================================================

def identify_document_type(case_description: str) -> str:
    """Identify the appropriate document type based on case description."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    # TODO: LLM classification
    return "petição inicial"


def build_argument_structure(document_type: str, facts: str, legal_issues: Dict) -> List[ArgumentBlock]:
    """Build the argument structure for the document."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    # TODO: Use doctrine from RAG + legal_issues to map arguments
    return []


def generate_blueprint(case_description: str, facts: str, legal_issues: Optional[Dict] = None) -> DraftBlueprint:
    """Main entry point: generate drafting blueprint."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    
    doc_type = identify_document_type(case_description)
    arguments = build_argument_structure(doc_type, facts, legal_issues or {})
    
    return DraftBlueprint(
        document_type=doc_type,
        competence="",
        facts_summary=facts,
        merits=arguments,
        observations=["Blueprint gerado — requer revisão humana antes de uso"],
    )
