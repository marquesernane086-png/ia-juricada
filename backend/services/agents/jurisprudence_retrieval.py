"""Jurisprudence Retrieval Agent

📚 PREPARATION MODE — NOT CONNECTED TO RUNTIME

Responsible for retrieving jurisprudence from a dedicated jurisprudential
index SEPARATE from doctrine.

Rules:
- NEVER mix doctrine and jurisprudence sources
- Prioritize tribunal hierarchy (STF > STJ > TJ > 1ª instância)
- Return precedents grouped by court
- Track binding precedents (súmulas vinculantes, temas repetitivos)

Future: will require a separate vector index for jurisprudence.
"""

ENABLED = False

from typing import Dict, List, Optional
from pydantic import BaseModel


# ============================================================
# SCHEMAS
# ============================================================

class JurisprudenceQuery(BaseModel):
    """Input: search parameters for jurisprudence."""
    legal_issue: str
    legal_area: str = ""
    court_filter: Optional[str] = None  # STF, STJ, TJRJ, etc.
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    binding_only: bool = False  # only súmulas vinculantes / temas


class Precedent(BaseModel):
    """A single judicial precedent."""
    court: str  # STF, STJ, TJSP, etc.
    case_number: str  # número do processo
    rapporteur: str  # relator
    judgment_date: str
    summary: str  # ementa
    thesis: str = ""  # tese fixada
    is_binding: bool = False  # vinculante?
    binding_type: str = ""  # súmula vinculante, tema repetitivo, IRDR
    relevance_score: float = 0.0


class JurisprudenceResult(BaseModel):
    """Output: grouped jurisprudence results."""
    query: str
    total_results: int = 0
    grouped_by_court: Dict[str, List[Precedent]] = {}
    binding_precedents: List[Precedent] = []
    hierarchy_note: str = ""


# ============================================================
# TRIBUNAL HIERARCHY
# ============================================================

COURT_HIERARCHY = {
    "STF": {"level": 1, "name": "Supremo Tribunal Federal", "binding": True},
    "STJ": {"level": 2, "name": "Superior Tribunal de Justiça", "binding": True},
    "TST": {"level": 2, "name": "Tribunal Superior do Trabalho", "binding": True},
    "TJ": {"level": 3, "name": "Tribunal de Justiça (estadual)", "binding": False},
    "TRF": {"level": 3, "name": "Tribunal Regional Federal", "binding": False},
    "TRT": {"level": 3, "name": "Tribunal Regional do Trabalho", "binding": False},
    "1ª instância": {"level": 4, "name": "Primeiro Grau", "binding": False},
}

BINDING_TYPES = [
    "Súmula Vinculante",
    "Tema de Repercussão Geral (STF)",
    "Tema de Recurso Repetitivo (STJ)",
    "IRDR (Incidente de Resolução de Demandas Repetitivas)",
    "IAC (Incidente de Assunção de Competência)",
]


# ============================================================
# CORE LOGIC (skeleton)
# ============================================================

def search_jurisprudence(query: JurisprudenceQuery) -> JurisprudenceResult:
    """Main entry point: search jurisprudence index."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    
    # TODO: Implement when jurisprudence index is created
    # 1. Search dedicated jurisprudence vector index
    # 2. Group by court
    # 3. Sort by hierarchy
    # 4. Identify binding precedents
    
    return JurisprudenceResult(
        query=query.legal_issue,
        hierarchy_note="Resultados ordenados por hierarquia: STF > STJ > TJ > 1ª instância",
    )


def check_binding_precedents(legal_issue: str) -> List[Precedent]:
    """Check for binding precedents on a legal issue."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    # TODO: Search súmulas vinculantes, temas repetitivos
    return []
