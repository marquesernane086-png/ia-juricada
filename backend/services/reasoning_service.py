"""Reasoning Service - Doctrinal legal reasoning engine using OpenAI."""

import os
import logging
from typing import List, Dict, Optional
from openai import OpenAI
from services.indexing_service import compute_temporal_weight

logger = logging.getLogger(__name__)

# System prompt for the legal reasoning AI
SYSTEM_PROMPT = """You are JuristaAI, a senior Brazilian legal scholar AI specialized in doctrinal reasoning.

Your role is to generate structured legal responses based on indexed legal books and references.

Use the following rules:

1. INPUT:
   - User legal question
   - Retrieved document chunks (from Legal Knowledge Indexer)
   - Metadata (author, title, year, edition, legal subject)

2. PROCESS:
   - Identify the legal issue
   - Retrieve relevant doctrine
   - Group findings by author and work
   - Detect divergences or evolution in understanding
   - Apply temporal weighting (prioritize newer editions but preserve historical context)
   - Integrate insights to highlight conflicting views

3. OUTPUT STRUCTURE:

## RELATÓRIO
- Summarize the doctrinal foundations
- Cite all authors accurately (AUTHOR, Work, Year)

## POSIÇÕES DOUTRINÁRIAS
- Compare classical and modern authors
- Explicitly highlight divergences or contradictions

## EVOLUÇÃO DO ENTENDIMENTO
- Describe changes in understanding over time or between editions

## CONCLUSÃO
- Provide a reasoned synthesis with clear recommendations or interpretations

4. GUIDELINES:
- Always prioritize doctrinal accuracy over brevity
- Do not hallucinate or invent citations
- Use structured headings exactly as above
- Assume all referenced materials come from indexed books
- Always link arguments to metadata of sources
- Maintain consistency with previous answers within the same session
- Treat each answer as a standalone academic legal note
- RESPOND IN PORTUGUESE (Brazilian Portuguese)
- When citing, use format: (AUTHOR. Title. Year)

5. TECHNICAL INTEGRATION:
- When retrieving content, respect vector search scores and chunk order
- Use semantic relevance as the first criterion for including content

IMPORTANT: If no relevant sources are found in the provided context, say so honestly.
Do NOT invent or fabricate citations. Only cite what is provided in the context."""


def get_openai_client() -> OpenAI:
    """Get configured OpenAI client."""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    base_url = os.environ.get('OPENAI_BASE_URL', 'https://ai-gateway.mywonder.xyz/v1')
    
    return OpenAI(
        api_key=api_key,
        base_url=base_url
    )


def group_by_author(results: List[Dict]) -> Dict[str, List[Dict]]:
    """Group search results by author for doctrinal comparison."""
    groups = {}
    for result in results:
        author = result.get("metadata", {}).get("author", "Autor Desconhecido")
        if not author:
            author = "Autor Desconhecido"
        if author not in groups:
            groups[author] = []
        groups[author].append(result)
    return groups


def apply_temporal_weighting(results: List[Dict]) -> List[Dict]:
    """Apply temporal weighting to results, boosting newer works."""
    for result in results:
        year = result.get("metadata", {}).get("year")
        if isinstance(year, str):
            try:
                year = int(year) if year else None
            except ValueError:
                year = None
        
        temporal_weight = compute_temporal_weight(year)
        original_score = result.get("score", 0.5)
        # Combine semantic score with temporal weight
        result["weighted_score"] = round(original_score * temporal_weight, 4)
        result["temporal_weight"] = temporal_weight
    
    # Sort by weighted score
    results.sort(key=lambda x: x.get("weighted_score", 0), reverse=True)
    return results


def detect_divergence(author_groups: Dict[str, List[Dict]]) -> List[Dict]:
    """Detect potential doctrinal divergence between authors.
    
    Returns a list of divergence indicators based on:
    - Different authors covering the same topic
    - Different years (evolution of understanding)
    """
    divergences = []
    
    authors = list(author_groups.keys())
    if len(authors) < 2:
        return divergences
    
    for i in range(len(authors)):
        for j in range(i + 1, len(authors)):
            author_a = authors[i]
            author_b = authors[j]
            
            years_a = [r["metadata"].get("year") for r in author_groups[author_a] if r["metadata"].get("year")]
            years_b = [r["metadata"].get("year") for r in author_groups[author_b] if r["metadata"].get("year")]
            
            divergences.append({
                "authors": [author_a, author_b],
                "years_a": years_a,
                "years_b": years_b,
                "has_temporal_gap": bool(years_a and years_b and 
                                        abs(max(years_a, default=0) - max(years_b, default=0)) > 10),
            })
    
    return divergences


def build_context(results: List[Dict]) -> str:
    """Build context string from search results for the LLM."""
    if not results:
        return "Nenhuma fonte doutrinária relevante foi encontrada no acervo indexado."
    
    author_groups = group_by_author(results)
    
    context_parts = []
    context_parts.append("=" * 60)
    context_parts.append("FONTES DOUTRINÁRIAS RECUPERADAS DO ACERVO")
    context_parts.append("=" * 60)
    
    for author, chunks in author_groups.items():
        context_parts.append(f"\n--- AUTOR: {author} ---")
        
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            title = meta.get("title", "Obra não identificada")
            year = meta.get("year", "s.d.")
            page = meta.get("page", "")
            score = chunk.get("weighted_score", chunk.get("score", 0))
            
            context_parts.append(f"\nObra: {title} ({year})")
            if page:
                context_parts.append(f"Página/Capítulo: {page}")
            context_parts.append(f"Relevância: {score:.2%}")
            context_parts.append(f"Trecho:\n{chunk['text']}")
            context_parts.append("-" * 40)
    
    # Add divergence info
    divergences = detect_divergence(author_groups)
    if divergences:
        context_parts.append(f"\n{'=' * 60}")
        context_parts.append("INDICADORES DE DIVERGÊNCIA DOUTRINÁRIA")
        context_parts.append("=" * 60)
        for div in divergences:
            context_parts.append(f"Autores: {div['authors'][0]} vs {div['authors'][1]}")
            if div['has_temporal_gap']:
                context_parts.append("⚠ Diferença temporal significativa (>10 anos)")
    
    return "\n".join(context_parts)


def generate_response(
    question: str,
    search_results: List[Dict],
    model: Optional[str] = None
) -> str:
    """Generate a structured doctrinal legal response.
    
    Args:
        question: User's legal question
        search_results: Retrieved document chunks with metadata
        model: LLM model to use
    
    Returns:
        Structured legal reasoning response
    """
    if model is None:
        model = os.environ.get('LLM_MODEL', 'gpt-4o-mini')
    
    client = get_openai_client()
    
    # Apply temporal weighting
    weighted_results = apply_temporal_weighting(search_results.copy())
    
    # Build context
    context = build_context(weighted_results)
    
    # Build user message
    user_message = f"""PERGUNTA JURÍDICA:
{question}

CONTEXTO DOUTRINÁRIO:
{context}

Responda com fundamentação doutrinária estruturada, citando as fontes fornecidas acima.
Se não houver fontes relevantes, informe honestamente."""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=4000,
        )
        
        answer = response.choices[0].message.content
        logger.info(f"Generated response: {len(answer)} chars, model: {model}")
        return answer
        
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return f"Erro ao gerar resposta doutrinária: {str(e)}"
