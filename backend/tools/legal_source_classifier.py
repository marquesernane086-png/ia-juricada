"""Legal Source Classifier — Classificador de Fonte Normativa (v2)

Classifica cada chunk juridico quanto a fonte normativa com precisao:
- constituicao
- sumula
- jurisprudencia (somente estrutura decisoria real)
- legislacao
- doutrina
- indefinido (capas, indices, OCR ruim)

Tambem detecta orgao julgador (com contexto decisorio) e artigos de lei.
Inclui hierarquia normativa com peso por fonte.

NAO altera embeddings, chunking, overlap ou checkpoint.
"""

import re


def detectar_jurisprudencia(texto: str) -> bool:
    """Detecta se o texto e jurisprudencia REAL (nao mera citacao doutrinaria).
    
    Exige estrutura decisoria: acordao, ementa, relator, julgado em, etc.
    """
    t = texto.lower()
    return bool(re.search(
        r"(ac[oó]rd[aã]o|ementa[:\s]|relator[:\s]|julgado em|data do julgamento|"
        r"recurso especial n[ºo°]|processo n[ºo°]|agravo interno n|"
        r"voto do relator|turma.*julgou|câmara.*decidiu|"
        r"dou provimento|negou provimento|conheceu.*recurso)",
        t
    ))


def detectar_fonte_normativa(texto: str) -> str:
    """Detecta tipo de fonte normativa do trecho.
    
    Returns: constituicao, sumula, jurisprudencia, legislacao, doutrina, ou indefinido
    """
    t = texto.lower()

    # Texto muito curto ou sem conteudo juridico = indefinido
    if len(t.strip()) < 80:
        return "indefinido"

    # Constituicao (referencia direta a dispositivo constitucional)
    if re.search(r"constitui[cç][aã]o federal|cf/88|cf de 1988|art\.?\s*\d+.*(?:da |,\s*)(?:cf|constitui)", t):
        return "constituicao"

    # Sumula (peso normativo proprio)
    if re.search(r"s[uú]mula\s+(?:vinculante\s+)?\d+", t):
        return "sumula"

    # Jurisprudencia (exige estrutura decisoria real)
    if detectar_jurisprudencia(texto):
        return "jurisprudencia"

    # Legislacao (referencia a lei, codigo, decreto)
    if re.search(
        r"lei n[º°]\s*\d|c[oó]digo civil|c[oó]digo penal|c[oó]digo de processo|"
        r"\bcpc\b|\bcdc\b|\bclt\b|\bcp\b.*art|decreto[\s-]lei|"
        r"medida provis[oó]ria|lei complementar|lei ordin[aá]ria",
        t
    ):
        return "legislacao"

    # Verificar se tem conteudo juridico minimo (evitar capas, indices, sumarios)
    sinais_juridicos = [
        "direito", "jurídic", "juridic", "doutrina", "autor", "obrigação", "obrigacao",
        "responsabilidade", "contrato", "culpa", "dano", "nexo", "ilícito", "ilicito",
        "legisla", "norma", "princípio", "principio", "artigo", "dispositivo",
    ]
    if not any(s in t for s in sinais_juridicos):
        return "indefinido"

    return "doutrina"


def detectar_orgao_julgador(texto: str) -> str:
    """Detecta orgao julgador com contexto decisorio (evita falso positivo).
    
    Exige que a mencao ao tribunal esteja em contexto de decisao,
    nao apenas citacao doutrinaria.
    """
    t = texto.lower()

    # So detecta orgao se houver contexto decisorio
    tem_contexto = bool(re.search(
        r"(ac[oó]rd[aã]o|ementa|relator|julgou|decidiu|provimento|recurso.*n[ºo°]|processo.*n[ºo°]|s[uú]mula)",
        t
    ))

    if not tem_contexto:
        return ""

    if "supremo tribunal federal" in t or re.search(r"\bstf\b", t):
        return "STF"

    if "superior tribunal de justi" in t or re.search(r"\bstj\b", t):
        return "STJ"

    if "tribunal superior do trabalho" in t or re.search(r"\btst\b", t):
        return "TST"

    if "tribunal regional federal" in t or re.search(r"\btrf\b", t):
        return "TRF"

    if "tribunal regional do trabalho" in t or re.search(r"\btrt\b", t):
        return "TRT"

    if "tribunal de justi" in t:
        return "TJ"

    return ""


def detectar_artigo(texto: str) -> str:
    """Detecta referencia a artigo de lei no texto.
    
    Returns: numero do artigo (ex: "927", "5") ou string vazia
    """
    m = re.search(r"art\.?\s*(\d+[A-Za-z\-]*)", texto.lower())
    return m.group(1) if m else ""


def peso_fonte(fonte: str) -> int:
    """Retorna peso da hierarquia normativa.
    
    Constituicao > Sumula > Jurisprudencia > Legislacao > Doutrina > Indefinido
    """
    pesos = {
        "constituicao": 5,
        "sumula": 4,
        "jurisprudencia": 3,
        "legislacao": 2,
        "doutrina": 1,
        "indefinido": 0,
    }
    return pesos.get(fonte, 0)


def classificar_fonte(texto: str) -> dict:
    """Classificacao completa da fonte juridica.
    
    Returns:
        {
            "fonte_normativa": "doutrina",
            "orgao_julgador": "",
            "artigo_referenciado": "927",
            "peso_normativo": 1
        }
    """
    fonte = detectar_fonte_normativa(texto)
    return {
        "fonte_normativa": fonte,
        "orgao_julgador": detectar_orgao_julgador(texto),
        "artigo_referenciado": detectar_artigo(texto),
        "peso_normativo": peso_fonte(fonte),
    }
