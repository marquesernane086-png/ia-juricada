"""Procedural Strategy Agent — Recursos Cabíveis

⚖️ PREPARATION MODE — NOT CONNECTED TO RUNTIME

Specializes in Brazilian procedural law analysis.
Determines the appropriate legal remedy (recurso cabível) based on
judicial decisions, procedural stage, and CPC rules.

When activated, this agent will:
1. Identify decision type (sentença, decisão interlocutória, despacho)
2. Detect jurisdiction level
3. Map procedural hypotheses defined in CPC
4. Determine applicable appeal, legal basis, deadline, effects

Constraints:
- Does NOT generate legal advice
- Does NOT draft petitions
- Only procedural classification
"""

ENABLED = False

from typing import Dict, List, Optional
from pydantic import BaseModel


# ============================================================
# SCHEMAS
# ============================================================

class DecisionInput(BaseModel):
    """Input: description or text of the judicial decision."""
    decision_text: str
    decision_type_hint: Optional[str] = None  # sentença, interlocutória, despacho
    jurisdiction: Optional[str] = None  # 1ª instância, TJ, STJ, STF
    procedural_stage: Optional[str] = None


class AppealOption(BaseModel):
    """A possible appeal/remedy."""
    appeal_name: str  # ex: Apelação, Agravo de Instrumento, REsp
    legal_basis: str  # ex: art. 1.009 CPC
    deadline_days: int  # prazo em dias úteis
    effects: str  # suspensivo, devolutivo, ambos
    requirements: List[str] = []  # requisitos de admissibilidade
    observations: str = ""


class ProceduralAnalysis(BaseModel):
    """Output: structured procedural analysis."""
    decision_type: str  # sentença, decisão interlocutória, despacho
    jurisdiction_level: str
    procedural_stage: str
    is_appealable: bool
    applicable_appeals: List[AppealOption] = []
    recommended_appeal: Optional[str] = None
    urgency_note: str = ""
    legal_observations: List[str] = []


# ============================================================
# DECISION TYPE CLASSIFICATION
# ============================================================

DECISION_TYPES = {
    "sentença": {
        "description": "Ato judicial que resolve o mérito ou extingue o processo sem mérito (art. 203, §1º, CPC)",
        "appeals": ["apelação"],
    },
    "decisão interlocutória": {
        "description": "Ato judicial que resolve questão incidente (art. 203, §2º, CPC)",
        "appeals": ["agravo de instrumento", "agravo interno"],
    },
    "despacho": {
        "description": "Ato judicial sem conteúdo decisório (art. 203, §3º, CPC)",
        "appeals": [],  # irrecorrível em regra
    },
}

# CPC Appeal mapping
APPEALS_DATABASE = {
    "apelação": AppealOption(
        appeal_name="Apelação",
        legal_basis="Art. 1.009 a 1.014, CPC",
        deadline_days=15,
        effects="suspensivo e devolutivo (regra)",
        requirements=["tempestividade", "preparo", "regularidade formal"],
    ),
    "agravo de instrumento": AppealOption(
        appeal_name="Agravo de Instrumento",
        legal_basis="Art. 1.015, CPC (rol taxativo mitigado — STJ Tema 988)",
        deadline_days=15,
        effects="devolutivo (suspensivo por decisão judicial)",
        requirements=["tempestividade", "hipótese do art. 1.015", "instrução obrigatória"],
        observations="Rol do art. 1.015 é taxativo, mas STJ admite mitigação (taxatividade mitigada)",
    ),
    "agravo interno": AppealOption(
        appeal_name="Agravo Interno",
        legal_basis="Art. 1.021, CPC",
        deadline_days=15,
        effects="devolutivo",
        requirements=["tempestividade", "impugnação específica"],
    ),
    "embargos de declaração": AppealOption(
        appeal_name="Embargos de Declaração",
        legal_basis="Art. 1.022, CPC",
        deadline_days=5,
        effects="interrompe prazo de outros recursos",
        requirements=["obscuridade, contradição, omissão ou erro material"],
    ),
    "recurso especial": AppealOption(
        appeal_name="Recurso Especial (REsp)",
        legal_basis="Art. 105, III, CF; Art. 1.029, CPC",
        deadline_days=15,
        effects="devolutivo",
        requirements=["prequestionamento", "esgotamento instâncias", "ofensa à lei federal"],
    ),
    "recurso extraordinário": AppealOption(
        appeal_name="Recurso Extraordinário (RE)",
        legal_basis="Art. 102, III, CF; Art. 1.029, CPC",
        deadline_days=15,
        effects="devolutivo",
        requirements=["prequestionamento", "repercussão geral", "ofensa constitucional"],
    ),
    "reclamação": AppealOption(
        appeal_name="Reclamação",
        legal_basis="Art. 988, CPC",
        deadline_days=0,  # sem prazo fixo
        effects="suspensivo por decisão",
        requirements=["preservar competência", "garantir autoridade de decisão"],
    ),
}


# ============================================================
# CORE LOGIC (skeleton)
# ============================================================

def classify_decision(decision_input: DecisionInput) -> str:
    """Classify the type of judicial decision."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    # TODO: Implement LLM-based or rule-based classification
    # Analyze decision_text for markers:
    # - "julgo procedente/improcedente" → sentença
    # - "defiro/indefiro" + incidental → interlocutória
    # - "cite-se", "intime-se" → despacho
    return "sentença"  # placeholder


def determine_appeals(decision_type: str, jurisdiction: str = "") -> List[AppealOption]:
    """Determine applicable appeals based on decision type."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    # TODO: Implement full CPC logic
    type_info = DECISION_TYPES.get(decision_type, {})
    appeal_names = type_info.get("appeals", [])
    return [APPEALS_DATABASE[name] for name in appeal_names if name in APPEALS_DATABASE]


def analyze(decision_input: DecisionInput) -> ProceduralAnalysis:
    """Main entry point: full procedural analysis."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    
    decision_type = classify_decision(decision_input)
    appeals = determine_appeals(decision_type)
    
    return ProceduralAnalysis(
        decision_type=decision_type,
        jurisdiction_level=decision_input.jurisdiction or "não identificado",
        procedural_stage=decision_input.procedural_stage or "não identificado",
        is_appealable=len(appeals) > 0,
        applicable_appeals=appeals,
        recommended_appeal=appeals[0].appeal_name if appeals else None,
    )
