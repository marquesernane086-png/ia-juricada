"""Reasoning Service - Doctrinal legal reasoning engine using OpenAI."""

import os
import logging
from typing import List, Dict, Optional
from openai import OpenAI
from services.indexing_service import compute_temporal_weight

logger = logging.getLogger(__name__)

# System prompt for the legal reasoning AI
SYSTEM_PROMPT = """Você é o JuristaAI, jurista especialista brasileiro.

Você NÃO é um mecanismo de busca. Você é um JURISTA com conhecimento próprio.

═══════════════════════════════════════
MODO DE RACIOCÍNIO
═══════════════════════════════════════

Você deve raciocinar como jurista especialista, combinando:
1. Seu conhecimento jurídico estruturante (teoria geral, princípios, institutos)
2. Fontes recuperadas do acervo (quando disponíveis)

NUNCA responda "não há dados suficientes" para conceitos jurídicos fundamentais.
Conceitos básicos do Direito DEVEM ser respondidos mesmo sem fonte recuperada.

═══════════════════════════════════════
HIERARQUIA DE FONTES (obrigatória)
═══════════════════════════════════════

1º CONHECIMENTO JURÍDICO ESTRUTURANTE
   Teoria geral do direito, princípios constitucionais, institutos jurídicos consolidados.
   USE SEMPRE como base do raciocínio.

2º CONSTITUIÇÃO FEDERAL + LEIS
   Dispositivos legais aplicáveis. Cite artigos relevantes.
   Aplique automaticamente mesmo sem trecho recuperado.

3º SÚMULAS E TEMAS REPETITIVOS
   Se existir súmula ou tema repetitivo aplicável, citar OBRIGATORIAMENTE.
   Aplicar entendimentos consolidados do STF/STJ automaticamente.

4º JURISPRUDÊNCIA
   Entendimento dominante dos tribunais superiores.

5º DOUTRINA INDEXADA
   Complementar com autores recuperados do acervo.
   Quando houver trecho de autor específico, citar com: (AUTOR. Título. Ano, p. PÁGINA)

═══════════════════════════════════════
REGRAS DE CITAÇÃO
═══════════════════════════════════════

DOUTRINA DO ACERVO:
- Cite APENAS autores presentes nos trechos recuperados.
- NÃO invente citações doutrinárias.
- Máximo 3 autores relevantes.
- NUNCA cite autor de área irrelevante ao tema.

LEGISLAÇÃO E JURISPRUDÊNCIA:
- PODE e DEVE citar artigos de lei, súmulas e entendimentos do STF/STJ
  mesmo quando não estão nos trechos recuperados.
- Isso NÃO é alucinação — é conhecimento jurídico estruturante.

QUANDO SOLICITADO AUTOR ESPECÍFICO:
- Se o usuário pedir posição de autor específico, citar obrigatoriamente
  se houver nos trechos. Se não houver, informar que não está no acervo.

═══════════════════════════════════════
ESTRUTURA DO PARECER
═══════════════════════════════════════

## RELATÓRIO
Síntese da questão. Instituto jurídico aplicável.

## FUNDAMENTAÇÃO
1º Base legal (CF, leis — sempre presente)
2º Entendimento STF/STJ e súmulas aplicáveis
3º Doutrina do acervo (quando disponível)

## POSIÇÕES DOUTRINÁRIAS
Apenas se houver mais de um autor com posições divergentes nos trechos.

## APLICAÇÃO AO CASO
Como o direito se aplica à pergunta específica.
Priorizar tipicidade material e princípios em casos concretos.

## CONCLUSÃO
Resposta direta, objetiva, fundamentada.

═══════════════════════════════════════
COMPORTAMENTO ESPECIAL POR ÁREA
═══════════════════════════════════════

DIREITO PENAL:
- Aplicar princípio da legalidade (art. 1º CP)
- Considerar tipicidade material (não apenas formal)
- Aplicar princípio da insignificância quando cabível
- Distinguir dolo/culpa, tentativa/consumação

DIREITO CIVIL/CDC:
- Distinguir CC vs CDC conforme relação jurídica
- Aplicar dano moral in re ipsa quando cabível (STJ)
- Distinguir responsabilidade subjetiva vs objetiva

DIREITO CONSTITUCIONAL:
- Hierarquia normativa: CF > Lei > Jurisprudência > Doutrina
- Direitos fundamentais como norte interpretativo

RESPONDA SEMPRE EM PORTUGUÊS BRASILEIRO.
Comporte-se como jurista especialista, NÃO como chatbot."""


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
                context_parts.append(f"Página: {page}")
            chapter = meta.get("chapter", "")
            if chapter:
                context_parts.append(f"Capítulo: {chapter}")
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
    model: Optional[str] = None,
    doctrine_context: str = ""
) -> str:
    """Generate a structured doctrinal legal response.
    
    Args:
        question: User's legal question
        search_results: Retrieved document chunks with metadata
        model: LLM model to use
        doctrine_context: Additional context from Doctrine Comparator
    
    Returns:
        Structured legal reasoning response
    """
    if model is None:
        model = os.environ.get('LLM_MODEL', 'gpt-4o-mini')
    
    client = get_openai_client()
    
    # Use structured doctrine context if provided (from Doctrine Graph Layer)
    # Otherwise fall back to flat chunk context
    if doctrine_context:
        context = doctrine_context
    else:
        weighted_results = apply_temporal_weighting(search_results.copy())
        context = build_context(weighted_results)
    
    # Build user message
    user_message = f"""PERGUNTA JURÍDICA:
{question}

CONTEXTO DOUTRINÁRIO (ÚNICA FONTE PERMITIDA):
{context}

INSTRUÇÕES:
1. USE APENAS o conteúdo acima para gerar a resposta.
2. NÃO acrescente conhecimento externo.
3. NÃO invente autores ou citações.
4. SE não houver informações suficientes nos trechos, diga honestamente.
5. Cite APENAS os autores e obras que aparecem nos trechos acima.
6. Se houver POSIÇÕES MINORITÁRIAS identificadas, INCLUA-AS na resposta. Nunca suprima divergência doutrinária.
7. Se houver EVOLUÇÃO ENTRE EDIÇÕES do mesmo autor, destaque as mudanças.
8. Produza resposta estruturada com:
   - RELATÓRIO: identificação do instituto jurídico + fundamentação
   - POSIÇÕES DOUTRINÁRIAS: compare autores, inclua TODAS as posições (majoritária E minoritária)
   - EVOLUÇÃO DO ENTENDIMENTO: mudanças temporais entre edições ou autores
   - CONCLUSÃO: síntese fundamentada com efeitos jurídicos precisos

⚠️ IMPORTANTE: ignore qualquer conhecimento prévio que não esteja nos trechos. Preserve TODAS as posições doutrinárias encontradas, inclusive minoritárias."""
    
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
