"""Jurisprudence Extractor — Extração estruturada de decisões judiciais.

Extrai metadados de decisões judiciais brasileiras:
- tribunal, processo, relator, data, órgão julgador
- tipo de decisão (acórdão, monocrática)
- ementa separada do texto integral

Projetado para STJ e STF inicialmente.
"""

import re
from typing import Dict, Optional


def extrair_metadados_decisao(texto: str, nome_arquivo: str = "") -> Dict:
    """Extrai metadados estruturados de uma decisão judicial.

    Args:
        texto: Texto integral da decisão
        nome_arquivo: Nome do arquivo (ajuda na detecção)

    Returns:
        Dict com metadados jurídicos
    """
    t = texto[:5000]  # primeiros 5000 chars para metadados
    t_lower = t.lower()

    meta = {
        "tribunal": _detectar_tribunal(t, nome_arquivo),
        "numero_processo": _extrair_numero_processo(t),
        "classe_processual": _extrair_classe(t),
        "relator": _extrair_relator(t),
        "data_julgamento": _extrair_data_julgamento(t),
        "orgao_julgador": _extrair_orgao_julgador(t),
        "tipo_decisao": _detectar_tipo_decisao(t_lower),
    }

    return meta


def extrair_ementa(texto: str) -> tuple:
    """Separa ementa do texto integral.

    Returns:
        (ementa, texto_sem_ementa)
    """
    # Padrões comuns de ementa
    patterns = [
        r'(?i)(EMENTA[:\s\-–]*)(.*?)(?=\n\s*(?:ACÓRDÃO|AC[OÓ]RD[AÃ]O|RELATÓRIO|RELAT[OÓ]RIO|Vistos|DECIDE|VOTO))',
        r'(?i)(EMENTA[:\s\-–]*)(.*?)(?=\n\n\n)',
        r'(?i)(EMENTA[:\s\-–]*)(.*?)(?=\n\s*\n\s*\n)',
    ]

    for pattern in patterns:
        match = re.search(pattern, texto, re.DOTALL)
        if match:
            ementa = match.group(2).strip()
            if len(ementa) > 50:
                # Remover ementa do texto
                texto_sem = texto[:match.start()] + texto[match.end():]
                return ementa, texto_sem

    return "", texto


def _detectar_tribunal(texto: str, nome_arquivo: str = "") -> str:
    """Detecta o tribunal de origem."""
    combined = (texto + " " + nome_arquivo).lower()

    tribunais = [
        (r'\bstf\b|supremo tribunal federal', "STF"),
        (r'\bstj\b|superior tribunal de justi[cç]a', "STJ"),
        (r'\btst\b|tribunal superior do trabalho', "TST"),
        (r'\btse\b|tribunal superior eleitoral', "TSE"),
        (r'\bstm\b|superior tribunal militar', "STM"),
        (r'trf[\s\-]*1|trf da 1', "TRF1"),
        (r'trf[\s\-]*2|trf da 2', "TRF2"),
        (r'trf[\s\-]*3|trf da 3', "TRF3"),
        (r'trf[\s\-]*4|trf da 4', "TRF4"),
        (r'trf[\s\-]*5|trf da 5', "TRF5"),
        (r'tjsp|tribunal de justi[cç]a.*s[aã]o paulo', "TJSP"),
        (r'tjrj|tribunal de justi[cç]a.*rio de janeiro', "TJRJ"),
        (r'tjmg|tribunal de justi[cç]a.*minas', "TJMG"),
        (r'tjrs|tribunal de justi[cç]a.*rio grande do sul', "TJRS"),
        (r'tribunal de justi[cç]a', "TJ"),
        (r'tribunal regional federal', "TRF"),
    ]

    for pattern, tribunal in tribunais:
        if re.search(pattern, combined):
            return tribunal

    return "desconhecido"


def _extrair_numero_processo(texto: str) -> str:
    """Extrai número do processo."""
    patterns = [
        r'(?:processo|proc\.|autos)\s*n[ºo°]?\s*([\d\.\-/]+)',
        r'(?:REsp|RE|HC|MS|AgRg|AgInt|EDcl)\s*n[ºo°]?\s*([\d\.\-/]+)',
        r'(\d{7}[\-\.]\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})',  # CNJ format
        r'n[ºo°]\s*([\d\.]+/[\d\-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, texto, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return "desconhecido"


def _extrair_classe(texto: str) -> str:
    """Extrai classe processual."""
    classes = [
        (r'recurso especial', "REsp"),
        (r'recurso extraordin[aá]rio', "RE"),
        (r'habeas corpus', "HC"),
        (r'mandado de seguran[cç]a', "MS"),
        (r'agravo interno', "AgInt"),
        (r'agravo regimental', "AgRg"),
        (r'agravo em recurso especial', "AREsp"),
        (r'embargos de declara[cç][aã]o', "EDcl"),
        (r'embargos de diverg[eê]ncia', "EREsp"),
        (r'a[cç][aã]o direta de inconstitucionalidade', "ADI"),
        (r'a[cç][aã]o declarat[oó]ria de constitucionalidade', "ADC"),
        (r'argui[cç][aã]o de descumprimento', "ADPF"),
        (r'reclama[cç][aã]o', "Rcl"),
        (r'conflito de compet[eê]ncia', "CC"),
        (r'apela[cç][aã]o', "Apelação"),
    ]

    t_lower = texto[:3000].lower()
    for pattern, classe in classes:
        if re.search(pattern, t_lower):
            return classe

    return "desconhecido"


def _extrair_relator(texto: str) -> str:
    """Extrai nome do relator."""
    patterns = [
        r'(?:relator|relatora|rel\.)[:\s]*(?:min(?:istro|istra)?\.?\s*)?([A-ZÀ-Ú][A-Za-zÀ-ú\s\.]+?)(?:\n|$|,|\()',
        r'(?:relator|relatora)[:\s]*([^\n,]{5,60})',
    ]

    for pattern in patterns:
        match = re.search(pattern, texto[:3000], re.IGNORECASE)
        if match:
            relator = match.group(1).strip()
            relator = re.sub(r'\s+', ' ', relator)
            if len(relator) > 3 and len(relator) < 60:
                return relator

    return "desconhecido"


def _extrair_data_julgamento(texto: str) -> str:
    """Extrai data do julgamento."""
    patterns = [
        r'(?:julgado em|data do julgamento|julgamento)[:\s]*(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})',
        r'(\d{1,2})\s*de\s*(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s*de\s*(\d{4})',
    ]

    for pattern in patterns:
        match = re.search(pattern, texto[:5000], re.IGNORECASE)
        if match:
            return match.group(0).strip()[:30]

    return "desconhecido"


def _extrair_orgao_julgador(texto: str) -> str:
    """Extrai órgão julgador (turma, câmara, seção)."""
    patterns = [
        r'(\d[aª°]\s*(?:turma|câmara|c[aâ]mara|se[cç][aã]o))',
        r'((?:primeira|segunda|terceira|quarta|quinta|sexta)\s*(?:turma|câmara|se[cç][aã]o))',
        r'(turma\s+\w+)',
        r'(plen[aá]rio|corte especial|tribunal pleno)',
    ]

    t_lower = texto[:3000].lower()
    for pattern in patterns:
        match = re.search(pattern, t_lower):
            return match.group(1).strip().title()

    return "desconhecido"


def _detectar_tipo_decisao(texto_lower: str) -> str:
    """Detecta tipo de decisão."""
    if re.search(r'ac[oó]rd[aã]o|a turma.*(?:decidiu|julgou)|por unanimidade|por maioria', texto_lower[:3000]):
        return "acordao"
    if re.search(r'decis[aã]o monocr[aá]tica|decido monocraticamente|decis[aã]o individual', texto_lower[:3000]):
        return "monocratica"
    if re.search(r'despacho', texto_lower[:1000]):
        return "despacho"
    return "desconhecido"
