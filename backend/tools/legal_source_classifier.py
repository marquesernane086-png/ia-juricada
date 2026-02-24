"""Legal Source Classifier — Classificador de Fonte Normativa

Classifica cada chunk de texto juridico quanto a sua fonte normativa:
- constituicao (Constituicao Federal)
- legislacao (leis, codigos)
- jurisprudencia (decisoes judiciais)
- doutrina (livros, artigos academicos)

Tambem detecta orgao julgador quando aplicavel (STF, STJ, TJ, TRF).

USO: chamar classificar_fonte(texto) para obter metadata adicional.

NAO altera embeddings, chunking, overlap ou checkpoint.
Apenas adiciona campos de metadata.
"""

import re


def detectar_fonte_normativa(texto: str) -> str:
    """Detecta o tipo de fonte normativa do trecho.
    
    Returns: constituicao, legislacao, jurisprudencia, ou doutrina
    """
    t = texto.lower()

    # Constituicao
    if re.search(r"constituição federal|constituicao federal|cf/88|cf de 1988|art\.?\s*\d+\s*da constituição|art\.?\s*\d+\s*da cf", t):
        return "constituicao"

    # Legislacao
    if re.search(r"lei n[º°]|código civil|codigo civil|código penal|codigo penal|cpc\b|cdc\b|c[oó]digo de processo|lei \d+\.\d+|decreto[\s-]lei|medida provis[oó]ria|lei complementar", t):
        return "legislacao"

    # Jurisprudencia
    if re.search(r"\bstj\b|\bstf\b|recurso especial|recurso extraordin[aá]rio|ac[oó]rd[aã]o|s[uú]mula|agravo|apela[cç][aã]o|habeas corpus|mandado de seguran[cç]a|TJSP|TJRJ|TJMG|TRF", t):
        return "jurisprudencia"

    # Default = doutrina
    return "doutrina"


def detectar_orgao_julgador(texto: str) -> str:
    """Detecta orgao julgador mencionado no texto.
    
    Returns: STF, STJ, TST, TJ, TRF, ou string vazia
    """
    t = texto.lower()

    if "supremo tribunal federal" in t or "stf" in t:
        return "STF"

    if "superior tribunal de justiça" in t or "superior tribunal de justica" in t or "stj" in t:
        return "STJ"

    if "tribunal superior do trabalho" in t or "tst" in t:
        return "TST"

    if "tribunal de justiça" in t or "tribunal de justica" in t:
        return "TJ"

    if "tribunal regional federal" in t:
        return "TRF"

    if "tribunal regional do trabalho" in t:
        return "TRT"

    return ""


def classificar_fonte(texto: str) -> dict:
    """Classificacao completa da fonte juridica do texto.
    
    Returns:
        {
            "fonte_normativa": "doutrina" | "legislacao" | "jurisprudencia" | "constituicao",
            "orgao_julgador": "STF" | "STJ" | "TJ" | "TRF" | "" 
        }
    """
    return {
        "fonte_normativa": detectar_fonte_normativa(texto),
        "orgao_julgador": detectar_orgao_julgador(texto),
    }
