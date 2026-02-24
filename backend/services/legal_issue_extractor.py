"""Legal Issue Extractor - Pre-retrieval question decomposition agent.

Transforms raw user questions into structured legal issues before vector search.
Improves retrieval quality by extracting precise legal concepts and keywords.

Pipeline position: FIRST — before vector retrieval.

Output: structured JSON with legal area, institute, core questions, keywords.
Does NOT answer, cite, or explain. Only decomposes.
"""

import os
import json
import logging
from typing import Dict, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Você é um classificador jurídico brasileiro. Sua ÚNICA função é decompor perguntas jurídicas em componentes estruturados.

NÃO responda a pergunta. NÃO cite doutrina. NÃO explique conceitos.
APENAS produza o JSON estruturado abaixo.

Regras:
- legal_area: área principal do direito (Direito Civil, Penal, Constitucional, Administrativo, Tributário, Trabalho, Empresarial, Processual Civil, Processual Penal, Ambiental, Consumidor, Internacional, ou Geral)
- legal_institute: instituto jurídico específico (ex: responsabilidade civil, vício redibitório, legítima defesa, habeas corpus, etc.)
- core_questions: as questões jurídicas centrais que a pergunta levanta (máximo 3)
- related_concepts: conceitos jurídicos relacionados que ajudam a encontrar doutrina relevante (máximo 5)
- keywords_for_retrieval: palavras-chave otimizadas para busca semântica em livros jurídicos brasileiros (máximo 8)
- controversy_points: pontos onde existe controvérsia doutrinária conhecida (máximo 3, pode ser vazio)

Responda APENAS com JSON válido, sem markdown, sem explicação."""

OUTPUT_SCHEMA = """{
  "legal_area": "",
  "legal_institute": "",
  "core_questions": [],
  "related_concepts": [],
  "keywords_for_retrieval": [],
  "controversy_points": []
}"""


def get_openai_client() -> OpenAI:
    """Get configured OpenAI client."""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    proxy_url = os.environ.get('INTEGRATION_PROXY_URL', 'https://integrations.emergentagent.com')
    base_url = f"{proxy_url}/llm"

    headers = {}
    app_url = os.environ.get('APP_URL') or os.environ.get('REACT_APP_BACKEND_URL', '')
    if app_url:
        headers['X-App-ID'] = app_url

    return OpenAI(api_key=api_key, base_url=base_url, default_headers=headers)


def extract_legal_issues(question: str, model: Optional[str] = None) -> Dict:
    """Decompose a user question into structured legal issues.

    Args:
        question: Raw user question in Portuguese
        model: LLM model to use

    Returns:
        Structured dict with legal decomposition
    """
    if model is None:
        model = os.environ.get('LLM_MODEL', 'gpt-4o-mini')

    # Default fallback in case of error
    default = {
        "legal_area": "Geral",
        "legal_institute": "",
        "core_questions": [question],
        "related_concepts": [],
        "keywords_for_retrieval": question.split()[:8],
        "controversy_points": [],
    }

    try:
        client = get_openai_client()

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": f"PERGUNTA: {question}\n\nESQUEMA DE SAÍDA:\n{OUTPUT_SCHEMA}"}
            ],
            temperature=0.1,
            max_tokens=500,
        )

        raw = response.choices[0].message.content.strip()

        # Clean potential markdown wrapping
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        if raw.endswith("```"):
            raw = raw[:-3]

        result = json.loads(raw.strip())

        # Validate required fields
        for key in ["legal_area", "legal_institute", "core_questions", "keywords_for_retrieval"]:
            if key not in result:
                result[key] = default[key]

        # Ensure lists
        for key in ["core_questions", "related_concepts", "keywords_for_retrieval", "controversy_points"]:
            if not isinstance(result.get(key), list):
                result[key] = default.get(key, [])

        logger.info(
            f"Legal Issue Extractor: area={result['legal_area']}, "
            f"institute={result['legal_institute']}, "
            f"keywords={result['keywords_for_retrieval']}"
        )

        return result

    except json.JSONDecodeError as e:
        logger.warning(f"Legal Issue Extractor: JSON parse error: {e}")
        return default
    except Exception as e:
        logger.warning(f"Legal Issue Extractor: error: {e}")
        return default


def build_enhanced_query(question: str, legal_issues: Dict) -> str:
    """Build an enhanced search query using extracted legal issues.

    Combines the original question with extracted keywords and concepts
    for better semantic search results.

    Args:
        question: Original user question
        legal_issues: Extracted legal issues dict

    Returns:
        Enhanced query string for vector search
    """
    parts = [question]

    # Add legal institute for precision
    institute = legal_issues.get("legal_institute", "")
    if institute and institute.lower() not in question.lower():
        parts.append(institute)

    # Add top keywords not already in question
    keywords = legal_issues.get("keywords_for_retrieval", [])
    for kw in keywords[:4]:
        if kw.lower() not in question.lower():
            parts.append(kw)

    enhanced = " ".join(parts)
    logger.info(f"Enhanced query: {enhanced[:120]}...")
    return enhanced
