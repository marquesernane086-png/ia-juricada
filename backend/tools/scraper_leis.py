"""Scraper de Leis — Extrai artigos do planalto.gov.br e gera JSONs

Uso:
    python scraper_leis.py

Gera arquivos em legal_sources/ prontos para indexar_leis.py
"""

import re
import json
import os
import logging
import requests
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("Scraper")

OUTPUT_DIR = "legal_sources"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def extrair_artigos(texto_html: str) -> List[Dict]:
    """Extrai artigos de texto de lei."""
    # Limpar HTML
    texto = re.sub(r'<[^>]+>', ' ', texto_html)
    texto = re.sub(r'&nbsp;', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)

    artigos = []

    # Pattern para artigos
    # Art. 1o, Art. 2º, Art. 186., Art. 927
    pattern = r'(Art\.?\s*(\d+[\-A-Za-z]*)[º°oa]?\.?\s*)(.*?)(?=Art\.?\s*\d+[\-A-Za-z]*[º°oa]?\.?\s|$)'

    for match in re.finditer(pattern, texto, re.DOTALL):
        num = match.group(2).strip()
        corpo = match.group(3).strip()

        # Limpar corpo
        corpo = re.sub(r'\s+', ' ', corpo)
        corpo = corpo.strip()

        if len(corpo) > 10 and num:
            artigos.append({
                "artigo": num,
                "texto": corpo[:2000]  # max 2000 chars por artigo
            })

    return artigos


LEIS = [
    {
        "url": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm",
        "nome": "Código Civil",
        "numero": "Lei 10.406/2002",
        "area": "Direito Civil",
        "hierarquia": "lei_federal",
        "arquivo": "codigo_civil_completo.json",
    },
    {
        "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm",
        "nome": "Código Penal",
        "numero": "Decreto-Lei 2.848/1940",
        "area": "Direito Penal",
        "hierarquia": "lei_federal",
        "arquivo": "codigo_penal.json",
    },
    {
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm",
        "nome": "Código de Processo Civil",
        "numero": "Lei 13.105/2015",
        "area": "Processo Civil",
        "hierarquia": "lei_federal",
        "arquivo": "codigo_processo_civil.json",
    },
    {
        "url": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",
        "nome": "Código de Defesa do Consumidor",
        "numero": "Lei 8.078/1990",
        "area": "Direito do Consumidor",
        "hierarquia": "lei_federal",
        "arquivo": "codigo_defesa_consumidor.json",
    },
    {
        "url": "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm",
        "nome": "Constituição Federal",
        "numero": "CF/1988",
        "area": "Direito Constitucional",
        "hierarquia": "constituicao",
        "arquivo": "constituicao_federal_completa.json",
    },
    {
        "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm",
        "nome": "Consolidação das Leis do Trabalho",
        "numero": "Decreto-Lei 5.452/1943",
        "area": "Direito do Trabalho",
        "hierarquia": "lei_federal",
        "arquivo": "clt.json",
    },
]


for lei in LEIS:
    logger.info(f"Baixando: {lei['nome']}...")

    try:
        r = requests.get(lei["url"], timeout=30)
        r.encoding = r.apparent_encoding or "utf-8"

        if r.status_code != 200:
            logger.error(f"  HTTP {r.status_code}")
            continue

        artigos = extrair_artigos(r.text)
        logger.info(f"  Artigos extraidos: {len(artigos)}")

        if not artigos:
            logger.warning(f"  Nenhum artigo encontrado")
            continue

        output = {
            "nome_norma": lei["nome"],
            "numero": lei["numero"],
            "area": lei["area"],
            "hierarquia": lei["hierarquia"],
            "vigencia": "ativa",
            "fonte": "planalto.gov.br",
            "artigos": artigos,
        }

        path = os.path.join(OUTPUT_DIR, lei["arquivo"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info(f"  Salvo: {path} ({len(artigos)} artigos)")

    except Exception as e:
        logger.error(f"  Erro: {e}")

logger.info("Concluido! Agora rode: python indexar_leis.py")
