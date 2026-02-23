"""Reasoning Service - Doctrinal legal reasoning engine using OpenAI."""

import os
import logging
from typing import List, Dict, Optional
from openai import OpenAI
from services.indexing_service import compute_temporal_weight

logger = logging.getLogger(__name__)

# System prompt for the legal reasoning AI
SYSTEM_PROMPT = """Você é o JuristaAI, um assistente jurídico doutrinário.

REGRA ABSOLUTA E INVIOLÁVEL:
Você SÓ pode usar informações que estão nos TRECHOS DOUTRINÁRIOS fornecidos abaixo como contexto.
Você NÃO pode usar seu conhecimento geral, treinamento ou qualquer informação externa.
Se a informação NÃO está nos trechos fornecidos, você NÃO sabe e deve dizer isso.

PROIBIÇÕES ESTRITAS:
- NUNCA invente citações, autores, obras ou argumentos que não estejam nos trechos fornecidos
- NUNCA complemente com conhecimento próprio do modelo de linguagem
- NUNCA cite artigos de lei, jurisprudência ou doutrina que não apareçam explicitamente nos trechos
- NUNCA "deduza" o que um autor diria — cite APENAS o que está escrito nos trechos
- NUNCA use frases como "é amplamente reconhecido" ou "a doutrina majoritária entende" sem que isso esteja nos trechos

O QUE FAZER:
- Responda EXCLUSIVAMENTE com base nos trechos doutrinários fornecidos
- Cite APENAS autores e obras que aparecem nos metadados dos trechos
- Use o formato de citação: (AUTOR. Título da Obra. Ano)
- Se os trechos são insuficientes para responder, diga claramente: "O acervo indexado não contém informações suficientes sobre este tema."
- Organize a resposta com as seções abaixo APENAS SE houver conteúdo suficiente nos trechos

ESTRUTURA DA RESPOSTA (quando houver fontes):

## RELATÓRIO
- Resuma APENAS o que os trechos fornecidos dizem sobre o tema
- Cite cada autor e obra conforme aparecem nos metadados

## POSIÇÕES DOUTRINÁRIAS
- Compare posições APENAS entre autores presentes nos trechos
- Destaque divergências APENAS se forem evidentes nos trechos

## EVOLUÇÃO DO ENTENDIMENTO
- Descreva evolução APENAS se os trechos de diferentes anos mostrarem mudanças

## CONCLUSÃO
- Sintetize APENAS o que os trechos permitem concluir
- Nunca extrapole além do que está nos trechos

RESPONDA SEMPRE EM PORTUGUÊS BRASILEIRO."""


def get_openai_client() -> OpenAI:
    """Get configured OpenAI client using Emergent proxy."""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    # Use Emergent integration proxy for LLM calls
    proxy_url = os.environ.get('INTEGRATION_PROXY_URL', 'https://integrations.emergentagent.com')
    base_url = f"{proxy_url}/llm"
    
    headers = {}
    # Add app identifier for Emergent routing
    app_url = os.environ.get('APP_URL') or os.environ.get('REACT_APP_BACKEND_URL', '')
    if app_url:
        headers['X-App-ID'] = app_url
    
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=headers
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

CONTEXTO DOUTRINÁRIO (ÚNICA FONTE PERMITIDA):
{context}

INSTRUÇÕES MUITO IMPORTANTES:
1. USE APENAS o conteúdo acima para gerar a resposta.
2. NÃO acrescente conhecimento externo.
3. NÃO invente autores ou citações.
4. SE não houver informações suficientes nos trechos, responda exatamente:
   "O acervo indexado não contém informações suficientes sobre este tema. Considere adicionar obras doutrinárias relacionadas."
5. Cite APENAS os autores e obras que aparecem nos trechos acima.
6. Produza resposta estruturada com:
   - RELATÓRIO: explicação do tema
   - POSIÇÕES DOUTRINÁRIAS: divergências se existirem
   - EVOLUÇÃO DO ENTENDIMENTO: histórico do tema
   - CONCLUSÃO: síntese fundamentada

⚠️ IMPORTANTE: ignore qualquer conhecimento prévio, regras gerais do direito, jurisprudência ou legislação que não esteja nos trechos."""
    
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
