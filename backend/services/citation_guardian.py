"""Citation Guardian - Post-generation citation validation agent.

Validates every citation in the LLM response against retrieved chunks.
Removes or flags hallucinated citations before delivering the response.

Pipeline position: AFTER reasoning, BEFORE response delivery.
"""

import re
import logging
from typing import List, Dict, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Normalize text for comparison (lowercase, remove accents, extra spaces)."""
    if not text:
        return ""
    text = text.lower().strip()
    # Remove common variations
    replacements = {
        "ç": "c", "ã": "a", "á": "a", "â": "a", "à": "a",
        "é": "e", "ê": "e", "í": "i", "ó": "o", "ô": "o",
        "ú": "u", "ü": "u", "ñ": "n",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return re.sub(r'\s+', ' ', text)


def _similarity(a: str, b: str) -> float:
    """Calculate string similarity ratio (0-1)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def extract_citations(response_text: str) -> List[Dict]:
    """Extract all citations from the LLM response text.
    
    Detects patterns like:
    - (AUTOR. Título. Ano, p. X)
    - (AUTOR. Título. Ano)
    - (AUTOR, Título, Ano, p. X)
    - (GONÇALVES. Responsabilidade Civil. 2012, p. 101)
    """
    citations = []
    
    patterns = [
        # (AUTOR. Título. Ano, p. X)
        r'\(([^()]+?)\.\s+([^()]+?)\.\s+(\d{4}),?\s*p\.\s*(\d+[^)]*)\)',
        # (AUTOR. Título. Ano)
        r'\(([^()]+?)\.\s+([^()]+?)\.\s+(\d{4})\)',
        # (AUTOR, Título, Ano, p. X)
        r'\(([^()]+?),\s+([^()]+?),\s+(\d{4}),?\s*p\.\s*(\d+[^)]*)\)',
        # (AUTOR, Título, Ano)
        r'\(([^()]+?),\s+([^()]+?),\s+(\d{4})\)',
    ]
    
    found_spans = set()  # Avoid duplicates from overlapping patterns
    
    for pattern in patterns:
        for match in re.finditer(pattern, response_text):
            span = (match.start(), match.end())
            if any(s[0] <= span[0] < s[1] for s in found_spans):
                continue
            found_spans.add(span)
            
            groups = match.groups()
            citation = {
                "author": groups[0].strip() if len(groups) > 0 else "",
                "title": groups[1].strip() if len(groups) > 1 else "",
                "year": int(groups[2]) if len(groups) > 2 else 0,
                "page": groups[3].strip() if len(groups) > 3 else "",
                "full_text": match.group(0),
                "position": span,
            }
            citations.append(citation)
    
    return citations


def validate_citation(citation: Dict, sources: List[Dict], threshold: float = 0.45) -> Dict:
    """Validate a single citation against retrieved source chunks.
    
    Args:
        citation: Extracted citation dict
        sources: List of retrieved chunks with metadata
        threshold: Minimum similarity for validation
    
    Returns:
        Validation result with status and details
    """
    best_match_score = 0.0
    best_match_source = None
    
    cite_author = citation.get("author", "")
    cite_title = citation.get("title", "")
    cite_year = citation.get("year", 0)
    
    for source in sources:
        meta = source.get("metadata", {})
        src_author = meta.get("author", "")
        src_title = meta.get("title", "")
        src_year = meta.get("year", "")
        
        # Convert year
        try:
            src_year_int = int(src_year) if src_year else 0
        except (ValueError, TypeError):
            src_year_int = 0
        
        # Calculate component scores
        author_sim = _similarity(cite_author, src_author)
        title_sim = _similarity(cite_title, src_title)
        year_match = 1.0 if (cite_year == src_year_int and cite_year > 0) else 0.0
        
        # Also check if author appears in title field (common in indexed data)
        author_in_title = _similarity(cite_author, src_title)
        
        # Weighted score: author most important, then title, then year
        score = (author_sim * 0.45) + (title_sim * 0.35) + (year_match * 0.20)
        
        # Bonus if author found in title field
        if author_in_title > 0.5:
            score = max(score, (author_in_title * 0.4) + (title_sim * 0.3) + (year_match * 0.3))
        
        if score > best_match_score:
            best_match_score = score
            best_match_source = {
                "author": src_author,
                "title": src_title,
                "year": src_year_int,
                "author_sim": round(author_sim, 3),
                "title_sim": round(title_sim, 3),
                "year_match": year_match,
            }
    
    is_valid = best_match_score >= threshold
    
    return {
        "citation": citation["full_text"],
        "valid": is_valid,
        "confidence": round(best_match_score, 3),
        "best_match": best_match_source,
        "reason": "validated" if is_valid else "no matching source found",
    }


def validate_response(response_text: str, sources: List[Dict]) -> Tuple[str, Dict]:
    """Validate all citations in a response and clean if needed.
    
    Args:
        response_text: The LLM-generated response
        sources: Retrieved chunks used as context
    
    Returns:
        Tuple of (cleaned_response, validation_report)
    """
    citations = extract_citations(response_text)
    
    if not citations:
        return response_text, {
            "total_citations": 0,
            "valid": 0,
            "invalid": 0,
            "details": [],
            "status": "no_citations_found",
        }
    
    validations = []
    valid_count = 0
    invalid_count = 0
    invalid_citations = []
    
    for citation in citations:
        result = validate_citation(citation, sources)
        validations.append(result)
        
        if result["valid"]:
            valid_count += 1
        else:
            invalid_count += 1
            invalid_citations.append(citation)
            logger.warning(
                f"Citation Guardian: INVALID citation detected: {citation['full_text']} "
                f"(confidence: {result['confidence']})"
            )
    
    # Clean response: flag invalid citations
    cleaned_response = response_text
    for citation in invalid_citations:
        original = citation["full_text"]
        flagged = f"{original} [⚠️ citação não verificada]"
        cleaned_response = cleaned_response.replace(original, flagged, 1)
    
    report = {
        "total_citations": len(citations),
        "valid": valid_count,
        "invalid": invalid_count,
        "details": validations,
        "status": "all_valid" if invalid_count == 0 else "has_invalid",
    }
    
    logger.info(
        f"Citation Guardian: {valid_count}/{len(citations)} citations validated, "
        f"{invalid_count} flagged"
    )
    
    return cleaned_response, report
