"""Legal Task Router — O Futuro Cérebro

🧭 PREPARATION MODE — NOT CONNECTED TO RUNTIME

Central orchestration agent responsible for deciding which specialized
agent should handle a user request.

Decision Logic:
  conceptual question  → Doctrine RAG (current pipeline)
  decision analysis    → Decision Analyzer
  appeal question      → Procedural Strategy
  deadline calculation → Deadline Agent
  document drafting    → Draft Generator
  case law request     → Jurisprudence Agent

When activated, this agent will be the FIRST in the pipeline,
replacing the current Legal Issue Extractor as the entry point.
"""

ENABLED = False

from typing import Dict, Optional
from pydantic import BaseModel


# ============================================================
# SCHEMAS
# ============================================================

class TaskClassification(BaseModel):
    """Output: classified task with routing decision."""
    task_type: str
    target_agent: str
    confidence: float = 0.0
    reasoning: str = ""
    requires_agents: list = []  # multiple agents if needed
    fallback_agent: str = "doctrine_rag"  # always fall back to doctrine


# ============================================================
# TASK TYPES AND ROUTING
# ============================================================

TASK_ROUTES = {
    "conceptual_question": {
        "description": "Pergunta conceitual sobre doutrina jurídica",
        "target": "doctrine_rag",
        "examples": [
            "O que é responsabilidade civil?",
            "Quais são os pressupostos do vício redibitório?",
            "Explique o princípio da legalidade.",
        ],
        "keywords": ["o que é", "conceito", "definição", "explique", "pressupostos", "requisitos"],
    },
    "decision_analysis": {
        "description": "Análise de decisão judicial",
        "target": "decision_analyzer",
        "examples": [
            "Analise esta sentença: ...",
            "Quais os pontos impugnáveis desta decisão?",
        ],
        "keywords": ["analise", "sentença", "decisão", "acórdão", "pontos impugnáveis"],
    },
    "appeal_strategy": {
        "description": "Estratégia recursal / recurso cabível",
        "target": "procedural_strategy",
        "examples": [
            "Qual recurso cabe contra decisão interlocutória?",
            "Posso recorrer de despacho?",
        ],
        "keywords": ["recurso cabível", "recorrer", "agravo", "apelação", "impugnar"],
    },
    "deadline_calculation": {
        "description": "Cálculo de prazo processual",
        "target": "deadline_agent",
        "examples": [
            "Qual o prazo para contestação?",
            "Quando vence o prazo para apelar se a publicação foi dia 10?",
        ],
        "keywords": ["prazo", "vencimento", "dias úteis", "quando vence", "contagem"],
    },
    "document_drafting": {
        "description": "Geração de estrutura de peça processual",
        "target": "legal_draft_generator",
        "examples": [
            "Monte a estrutura de uma petição inicial de indenização.",
            "Qual a estrutura de um agravo de instrumento?",
        ],
        "keywords": ["petição", "peça", "redigir", "estrutura", "modelo", "elaborar"],
    },
    "jurisprudence_search": {
        "description": "Busca de jurisprudência",
        "target": "jurisprudence_retrieval",
        "examples": [
            "Qual a jurisprudência do STJ sobre dano moral?",
            "Tem súmula sobre responsabilidade bancária?",
        ],
        "keywords": ["jurisprudência", "súmula", "precedente", "STF", "STJ", "tribunal"],
    },
}


# ============================================================
# CORE LOGIC (skeleton)
# ============================================================

def classify_task(user_input: str) -> TaskClassification:
    """Classify user input and determine which agent should handle it."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    
    input_lower = user_input.lower()
    best_match = None
    best_score = 0
    
    for task_type, config in TASK_ROUTES.items():
        score = 0
        for keyword in config["keywords"]:
            if keyword in input_lower:
                score += 1
        
        if score > best_score:
            best_score = score
            best_match = task_type
    
    if not best_match or best_score == 0:
        best_match = "conceptual_question"  # default to doctrine
    
    route = TASK_ROUTES[best_match]
    
    return TaskClassification(
        task_type=best_match,
        target_agent=route["target"],
        confidence=min(best_score / 3.0, 1.0),
        reasoning=route["description"],
    )


def route_request(user_input: str) -> Dict:
    """Main entry point: classify and route a user request."""
    if not ENABLED:
        raise RuntimeError("Agent not activated")
    
    classification = classify_task(user_input)
    
    return {
        "task_type": classification.task_type,
        "target_agent": classification.target_agent,
        "confidence": classification.confidence,
        "reasoning": classification.reasoning,
        "status": "routed",
    }
