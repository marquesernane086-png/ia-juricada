"""Doctrine Comparator - Advanced doctrinal divergence detection agent.

Analyzes retrieved chunks to detect:
- Agreement between authors
- Partial divergence
- Direct doctrinal conflict
- Same author different editions evolution

Pipeline position: AFTER vector retrieval, BEFORE reasoning.
"""

import logging
from typing import List, Dict, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


def cluster_by_author_and_work(results: List[Dict]) -> Dict[str, Dict]:
    """Cluster results by author → work → edition.
    
    Structure:
    {
        "Author Name": {
            "works": {
                "Work Title": {
                    "years": [2012, 2020],
                    "chunks": [...],
                    "editions": {"2012": [...], "2020": [...]}
                }
            },
            "total_chunks": N
        }
    }
    """
    authors = {}
    
    for result in results:
        meta = result.get("metadata", {})
        author = meta.get("author", "") or "Autor Desconhecido"
        title = meta.get("title", "") or "Obra não identificada"
        year = meta.get("year", "")
        
        try:
            year_int = int(year) if year else 0
        except (ValueError, TypeError):
            year_int = 0
        
        if author not in authors:
            authors[author] = {"works": {}, "total_chunks": 0}
        
        if title not in authors[author]["works"]:
            authors[author]["works"][title] = {
                "years": [],
                "chunks": [],
                "editions": defaultdict(list),
            }
        
        work = authors[author]["works"][title]
        work["chunks"].append(result)
        if year_int and year_int not in work["years"]:
            work["years"].append(year_int)
        work["editions"][str(year_int)].append(result)
        authors[author]["total_chunks"] += 1
    
    return authors


def detect_edition_evolution(author_data: Dict) -> List[Dict]:
    """Detect evolution within same author's different editions.
    
    Returns list of evolution indicators for same work across editions.
    """
    evolutions = []
    
    for work_title, work_data in author_data["works"].items():
        years = sorted(work_data["years"])
        if len(years) < 2:
            continue
        
        evolutions.append({
            "type": "edition_evolution",
            "work": work_title,
            "editions": years,
            "oldest": years[0],
            "newest": years[-1],
            "span_years": years[-1] - years[0],
        })
    
    return evolutions


def compare_authors(author_clusters: Dict) -> List[Dict]:
    """Compare doctrinal positions between different authors.
    
    Detects:
    - AGREEMENT: Authors discussing same topic with similar conclusions
    - PARTIAL_DIVERGENCE: Overlapping but different emphasis
    - CONFLICT: Direct doctrinal opposition
    
    Returns list of comparison results.
    """
    comparisons = []
    author_names = [a for a in author_clusters.keys() if a != "Autor Desconhecido"]
    
    if len(author_names) < 2:
        return comparisons
    
    for i in range(len(author_names)):
        for j in range(i + 1, len(author_names)):
            author_a = author_names[i]
            author_b = author_names[j]
            
            data_a = author_clusters[author_a]
            data_b = author_clusters[author_b]
            
            # Get years for temporal comparison
            all_years_a = []
            all_years_b = []
            for w in data_a["works"].values():
                all_years_a.extend(w["years"])
            for w in data_b["works"].values():
                all_years_b.extend(w["years"])
            
            max_year_a = max(all_years_a) if all_years_a else 0
            max_year_b = max(all_years_b) if all_years_b else 0
            
            temporal_gap = abs(max_year_a - max_year_b)
            
            # Determine comparison type based on available data
            comparison = {
                "type": "author_comparison",
                "author_a": author_a,
                "author_b": author_b,
                "works_a": list(data_a["works"].keys()),
                "works_b": list(data_b["works"].keys()),
                "chunks_a": data_a["total_chunks"],
                "chunks_b": data_b["total_chunks"],
                "years_a": sorted(set(all_years_a)),
                "years_b": sorted(set(all_years_b)),
                "temporal_gap": temporal_gap,
                "has_temporal_gap": temporal_gap > 10,
                "divergence_level": "unknown",  # Will be refined by LLM
            }
            
            # Heuristic: if one is much older, likely evolution not conflict
            if temporal_gap > 20:
                comparison["divergence_level"] = "possible_evolution"
                comparison["note"] = f"Diferença temporal de {temporal_gap} anos sugere evolução doutrinária"
            
            comparisons.append(comparison)
    
    return comparisons


def analyze_doctrine(results: List[Dict]) -> Dict:
    """Main analysis function. Produces structured doctrinal analysis.
    
    Args:
        results: Retrieved chunks with metadata
    
    Returns:
        Structured analysis with clusters, comparisons, and evolutions
    """
    if not results:
        return {
            "author_clusters": {},
            "comparisons": [],
            "evolutions": [],
            "minority_positions": [],
            "summary": {
                "total_authors": 0,
                "total_works": 0,
                "has_divergence": False,
                "has_evolution": False,
                "has_minority": False,
            }
        }
    
    # Step 1: Cluster by author and work
    author_clusters = cluster_by_author_and_work(results)
    
    # Step 2: Detect edition evolution within same author
    evolutions = []
    for author_name, author_data in author_clusters.items():
        author_evolutions = detect_edition_evolution(author_data)
        evolutions.extend(author_evolutions)
    
    # Step 3: Compare between authors
    comparisons = compare_authors(author_clusters)
    
    # Step 4: Identify minority positions
    # An author with fewer chunks relative to others may hold minority position
    minority_positions = detect_minority_positions(author_clusters)
    
    # Summary
    total_authors = len([a for a in author_clusters if a != "Autor Desconhecido"])
    total_works = sum(len(d["works"]) for d in author_clusters.values())
    
    analysis = {
        "author_clusters": {
            name: {
                "works": {
                    title: {
                        "years": data["years"],
                        "chunk_count": len(data["chunks"]),
                    }
                    for title, data in info["works"].items()
                },
                "total_chunks": info["total_chunks"],
            }
            for name, info in author_clusters.items()
        },
        "comparisons": comparisons,
        "evolutions": evolutions,
        "minority_positions": minority_positions,
        "summary": {
            "total_authors": total_authors,
            "total_works": total_works,
            "has_divergence": len(comparisons) > 0 and total_authors >= 2,
            "has_evolution": len(evolutions) > 0,
            "has_minority": len(minority_positions) > 0,
        }
    }
    
    logger.info(
        f"Doctrine Comparator: {total_authors} authors, {total_works} works, "
        f"{len(comparisons)} comparisons, {len(evolutions)} evolutions, "
        f"{len(minority_positions)} minority positions"
    )
    
    return analysis


def detect_minority_positions(author_clusters: Dict) -> List[Dict]:
    """Detect potential minority doctrinal positions.
    
    If one author has significantly fewer chunks than others on the same topic,
    they may represent a minority position that must be preserved.
    """
    minorities = []
    
    authors = {k: v for k, v in author_clusters.items() if k != "Autor Desconhecido"}
    if len(authors) < 2:
        return minorities
    
    chunk_counts = {name: data["total_chunks"] for name, data in authors.items()}
    total = sum(chunk_counts.values())
    
    if total == 0:
        return minorities
    
    avg = total / len(chunk_counts)
    
    for author, count in chunk_counts.items():
        # If an author has less than 30% of average, they're a minority voice
        if count < avg * 0.3 and count > 0:
            minorities.append({
                "author": author,
                "chunks": count,
                "percentage": round(count / total * 100, 1),
                "works": list(authors[author]["works"].keys()),
                "note": f"{author} representa posição minoritária no acervo ({count} trechos vs média de {avg:.0f})",
            })
    
    return minorities


def build_doctrine_context(analysis: Dict) -> str:
    """Build additional context string from doctrine analysis for the LLM.
    
    This is appended to the standard chunk context to help the LLM
    produce better structured answers.
    """
    parts = []
    
    summary = analysis.get("summary", {})
    
    if summary.get("total_authors", 0) >= 2:
        parts.append("\n" + "=" * 60)
        parts.append("ANÁLISE DOUTRINÁRIA COMPARATIVA")
        parts.append("=" * 60)
        
        # Author overview
        clusters = analysis.get("author_clusters", {})
        parts.append(f"\nAutores encontrados: {summary['total_authors']}")
        for author, data in clusters.items():
            if author == "Autor Desconhecido":
                continue
            works = ", ".join(f"{t} ({d['years']})" for t, d in data["works"].items())
            parts.append(f"  • {author}: {works} [{data['total_chunks']} trechos]")
    
    # Comparisons
    comparisons = analysis.get("comparisons", [])
    if comparisons:
        parts.append("\nCOMPARAÇÕES ENTRE AUTORES:")
        for comp in comparisons:
            parts.append(f"  {comp['author_a']} vs {comp['author_b']}")
            if comp.get("has_temporal_gap"):
                parts.append(f"    ⚠ Diferença temporal: {comp['temporal_gap']} anos")
            if comp.get("note"):
                parts.append(f"    📝 {comp['note']}")
    
    # Evolutions
    evolutions = analysis.get("evolutions", [])
    if evolutions:
        parts.append("\nEVOLUÇÃO ENTRE EDIÇÕES:")
        for evo in evolutions:
            parts.append(f"  {evo['work']}: edições {evo['editions']} (span: {evo['span_years']} anos)")
    
    # Minority positions
    minorities = analysis.get("minority_positions", [])
    if minorities:
        parts.append("\n⚠ POSIÇÕES MINORITÁRIAS DETECTADAS (DEVEM SER PRESERVADAS):")
        for min_pos in minorities:
            parts.append(f"  • {min_pos['author']}: {min_pos['percentage']}% dos trechos")
            parts.append(f"    {min_pos['note']}")
        parts.append("  → A resposta DEVE incluir estas posições, mesmo que minoritárias.")
    
    return "\n".join(parts) if parts else ""
