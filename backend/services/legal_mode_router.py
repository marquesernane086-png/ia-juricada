"""Legal Mode Router — Detecta tipo de consulta jurídica.

Modos:
  ACADEMIC     → pergunta doutrinária
  ADVOCACY     → estratégia/processo/peça
  JUDICIAL     → análise objetiva tipo magistrado
  PROCEDURAL   → prazo, recurso, competência

NÃO conectado ao pipeline. Ativar via LEGAL_MODE_ROUTER_ENABLED=true
"""

import os
import logging
from enum import Enum
from typing import Dict

logger = logging.getLogger(__name__)

ENABLED = os.environ.get("LEGAL_MODE_ROUTER_ENABLED", "false").lower() == "true"


class LegalMode(str, Enum):
    ACADEMIC = "academic"
    ADVOCACY = "advocacy"
    JUDICIAL = "judicial"
    PROCEDURAL = "procedural"


KEYWORD_MAP = {
    LegalMode.PROCEDURAL: [
        "prazo", "recurso cabível", "agravo", "apelação", "embargo",
        "competência", "dias úteis", "quando vence", "contagem",
        "tempestividade", "efeito suspensivo", "devolutivo",
    ],
    LegalMode.ADVOCACY: [
        "estratégia", "peça", "petição", "contestação", "como argumentar",
        "tese", "fundamentar", "redigir", "elaborar", "defender",
        "impugnar", "requerer", "tutela", "liminar", "cautelar",
    ],
    LegalMode.JUDICIAL: [
        "analise esta sentença", "analise esta decisão", "pontos impugnáveis",
        "risco de reforma", "fundamentação adequada", "nulidade",
        "acórdão", "voto", "dispositivo", "julgue", "decida",
    ],
    LegalMode.ACADEMIC: [
        "o que é", "conceito", "defina", "explique", "pressupostos",
        "requisitos", "natureza jurídica", "classificação", "doutrina",
        "segundo", "autor", "comparação", "evolução", "história",
    ],
}


def detect_legal_mode(question: str) -> Dict:
    """Detecta modo jurídico da pergunta.

    Returns:
        {"mode": LegalMode, "confidence": float, "scores": dict}
    """
    q = question.lower()
    scores = {}

    for mode, keywords in KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if kw in q)
        if score > 0:
            scores[mode.value] = score

    if not scores:
        result = {"mode": LegalMode.ACADEMIC, "confidence": 0.3, "scores": {}}
    else:
        best = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = round(scores[best] / max(total, 1), 2)
        result = {"mode": LegalMode(best), "confidence": confidence, "scores": scores}

    logger.info(f"[ModeRouter] {result['mode'].value} (conf: {result['confidence']}) for: {question[:60]}")
    return result


def get_system_prompt_for_mode(mode: LegalMode) -> str:
    """Retorna path do prompt para o modo."""
    prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
    mapping = {
        LegalMode.ACADEMIC: "academic_reasoning.txt",
        LegalMode.ADVOCACY: "lawyer_reasoning.txt",
        LegalMode.JUDICIAL: "judge_reasoning.txt",
        LegalMode.PROCEDURAL: "lawyer_reasoning.txt",
    }
    path = os.path.join(prompts_dir, mapping.get(mode, "academic_reasoning.txt"))
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""
