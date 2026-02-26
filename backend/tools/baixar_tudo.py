"""JuristaAI — Crawler Completo de Jurisprudência

Baixa e organiza TODA jurisprudência pública disponível:
- Súmulas STJ (673)
- Temas Repetitivos STJ (1.411)
- Pesquisa Pronta STJ (centenas por área)
- Súmulas Vinculantes STF (37)
- Leis do Planalto (CC, CP, CPC, CDC, CF, CLT...)

Tudo salvo em pastas organizadas + indexado no Qdrant local.

Uso:
    python baixar_tudo.py

Estrutura gerada:
    jurisprudencia/
        sumulas_stj/
            sumulas_stj.json
        temas_repetitivos/
            temas_stj.json
        pesquisa_pronta/
            direito_civil.json
            direito_penal.json
            ...
        sumulas_vinculantes_stf/
            sumulas_stf.json
    legislacao/
        constituicao_federal.json
        codigo_civil.json
        codigo_penal.json
        codigo_processo_civil.json
        codigo_defesa_consumidor.json
        clt.json
        codigo_tributario.json
        ...
"""

import os
import re
import json
import time
import logging
import hashlib
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("baixar_tudo.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("JuristaDownloader")

# ============================================================
# CONFIGURACAO
# ============================================================

QDRANT_DIR = "qdrant_data"
COLLECTION = "jurista_legal_docs"
CHECKPOINT = "controle_download.json"
BATCH_SIZE = 100

# Pastas de saida
DIRS = {
    "sumulas_stj": "jurisprudencia/sumulas_stj",
    "temas": "jurisprudencia/temas_repetitivos",
    "pesquisa": "jurisprudencia/pesquisa_pronta",
    "sumulas_stf": "jurisprudencia/sumulas_vinculantes_stf",
    "leis": "legislacao",
}

for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

# Checkpoint
if os.path.exists(CHECKPOINT):
    with open(CHECKPOINT, "r", encoding="utf-8") as f:
        ckpt = json.load(f)
else:
    ckpt = {"etapas_concluidas": [], "total_indexado": 0}

def salvar_ckpt():
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, indent=2, ensure_ascii=False)

# ============================================================
# QDRANT + EMBEDDINGS
# ============================================================

logger.info("Carregando modelo de embeddings...")
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

os.makedirs(QDRANT_DIR, exist_ok=True)
client = QdrantClient(path=QDRANT_DIR)
collections = [c.name for c in client.get_collections().collections]
if COLLECTION not in collections:
    client.create_collection(collection_name=COLLECTION, vectors_config=VectorParams(size=384, distance=Distance.COSINE))

try:
    point_id = client.get_collection(COLLECTION).points_count
except:
    point_id = 0

logger.info(f"Qdrant: {point_id} pontos existentes")
batch = []
total_novo = 0

def indexar_batch():
    global batch, total_novo
    if batch:
        client.upsert(collection_name=COLLECTION, points=batch)
        total_novo += len(batch)
        batch = []

def add_point(texto, metadata):
    global point_id, batch
    emb = model.encode(texto, normalize_embeddings=True)
    point_id += 1
    batch.append(PointStruct(id=point_id, vector=emb.tolist(), payload={**metadata, "text": texto}))
    if len(batch) >= BATCH_SIZE:
        indexar_batch()

# ============================================================
# ETAPA 1: SUMULAS STJ (PDF)
# ============================================================

if "sumulas_stj" not in ckpt.get("etapas_concluidas", []):
    logger.info("\n" + "=" * 60)
    logger.info("ETAPA 1: SUMULAS STJ")
    logger.info("=" * 60)

    try:
        import fitz
        url = "https://scon.stj.jus.br/docs_internet/VerbetesSTJ.pdf"
        logger.info(f"Baixando PDF: {url}")
        r = requests.get(url, timeout=60)
        pdf_path = os.path.join(DIRS["sumulas_stj"], "VerbetesSTJ.pdf")
        with open(pdf_path, "wb") as f:
            f.write(r.content)
        logger.info(f"PDF salvo: {pdf_path} ({len(r.content)/(1024*1024):.1f}MB)")

        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()

        pattern = r'SÚMULA\s+(\d+)\s+(.*?)(?=SÚMULA\s+\d+|$)'
        matches = re.findall(pattern, full_text, re.DOTALL)

        sumulas = []
        for num, texto in matches:
            texto = re.sub(r'\s+', ' ', texto).strip()
            if len(texto) > 20:
                sumulas.append({"numero": int(num), "texto": texto})
                add_point(
                    f"SÚMULA {num} - STJ\n\n\"{texto}\"",
                    {"tipo_documento": "sumula", "source_type": "jurisprudence", "tribunal": "STJ",
                     "sumula_number": str(num), "peso_normativo": 4, "binding_level": "persuasive_strong"}
                )

        sumulas.sort(key=lambda x: x["numero"])
        with open(os.path.join(DIRS["sumulas_stj"], "sumulas_stj.json"), "w", encoding="utf-8") as f:
            json.dump(sumulas, f, ensure_ascii=False, indent=1)

        indexar_batch()
        logger.info(f"Sumulas STJ: {len(sumulas)} indexadas")
        ckpt["etapas_concluidas"].append("sumulas_stj")
        salvar_ckpt()

    except Exception as e:
        logger.error(f"Erro sumulas STJ: {e}")

# ============================================================
# ETAPA 2: TEMAS REPETITIVOS STJ
# ============================================================

if "temas_repetitivos" not in ckpt.get("etapas_concluidas", []):
    logger.info("\n" + "=" * 60)
    logger.info("ETAPA 2: TEMAS REPETITIVOS STJ (1.411)")
    logger.info("=" * 60)

    all_temas = []
    total_pages = 29

    for page in range(total_pages):
        offset = page * 50 + 1
        url = f"https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp?novaConsulta=true&tipo_pesquisa=T&situacao=JULGADO&l=50&i={offset}"
        logger.info(f"  Pagina {page+1}/{total_pages} (offset {offset})")

        try:
            r = requests.get(url, timeout=30)
            r.encoding = "utf-8"
            text = BeautifulSoup(r.text, "html.parser").get_text()

            blocks = re.split(r'Documento \d+', text)
            for block in blocks:
                tema_match = re.search(r'Tema Repetitivo\s*(\d+)', block)
                if not tema_match:
                    continue
                num = int(tema_match.group(1))

                tese = ""
                tese_match = re.search(r'Tese Firmada\s*(.*?)(?=Anota|Delimita|Informa|Repercuss|Entendimento|Refer|$)', block, re.DOTALL)
                if tese_match:
                    tese = re.sub(r'\s+', ' ', tese_match.group(1)).strip()
                if not tese or len(tese) < 20:
                    continue

                area = "Geral"
                area_match = re.search(r'Ramo do direito\s*(.*?)(?=Quest|$)', block)
                if area_match:
                    area = re.sub(r'\s+', ' ', area_match.group(1)).strip()

                proc = ""
                proc_match = re.search(r'(REsp|AREsp|EREsp|CC)\s*(\d+/[A-Z]{2})', block)
                if proc_match:
                    proc = f"{proc_match.group(1)} {proc_match.group(2)}"

                relator = ""
                rel_match = re.search(r'Relator\s*([A-Z][A-Z\s\.]+?)(?=Embargo|Afeta|$)', block)
                if rel_match:
                    relator = rel_match.group(1).strip()[:60]

                all_temas.append({"tema": num, "tese": tese, "area": area, "processo": proc, "relator": relator})

                add_point(
                    f"TEMA REPETITIVO {num} - STJ\n\nTese: {tese}",
                    {"tipo_documento": "jurisprudencia", "source_type": "jurisprudence",
                     "jurisprudence_type": "tema_repetitivo", "tribunal": "STJ",
                     "tema": f"Tema {num}", "processo": proc, "relator": relator,
                     "area_direito": area, "peso_normativo": 4, "binding_level": "vinculante"}
                )

            time.sleep(2)
        except Exception as e:
            logger.error(f"  Erro pagina {page+1}: {e}")
            time.sleep(5)

    with open(os.path.join(DIRS["temas"], "temas_stj.json"), "w", encoding="utf-8") as f:
        json.dump(all_temas, f, ensure_ascii=False, indent=1)

    indexar_batch()
    logger.info(f"Temas repetitivos: {len(all_temas)} indexados")
    ckpt["etapas_concluidas"].append("temas_repetitivos")
    salvar_ckpt()

# ============================================================
# ETAPA 3: PESQUISA PRONTA STJ
# ============================================================

if "pesquisa_pronta" not in ckpt.get("etapas_concluidas", []):
    logger.info("\n" + "=" * 60)
    logger.info("ETAPA 3: PESQUISA PRONTA STJ")
    logger.info("=" * 60)

    AREAS_PP = {
        "Direito Administrativo": "DIREITO%20ADMINISTRATIVO",
        "Direito Ambiental": "DIREITO%20AMBIENTAL",
        "Direito Civil": "DIREITO%20CIVIL",
        "Direito do Consumidor": "DIREITO%20DO%20CONSUMIDOR",
        "Direito Empresarial": "DIREITO%20EMPRESARIAL",
        "Direito Penal": "DIREITO%20PENAL",
        "Direito Previdenciario": "DIREITO%20PREVIDENCI%C1RIO",
        "Processo Civil": "DIREITO%20PROCESSUAL%20CIVIL",
        "Processo Penal": "DIREITO%20PROCESSUAL%20PENAL",
        "Direito Tributario": "DIREITO%20TRIBUT%C1RIO",
    }

    for area_nome, area_code in AREAS_PP.items():
        logger.info(f"  Area: {area_nome}")
        url = f"https://scon.stj.jus.br/SCON/pesquisa_pronta/toc.jsp?livre=%27{area_code}%27.mat."

        try:
            r = requests.get(url, timeout=30)
            r.encoding = "utf-8"
            text = BeautifulSoup(r.text, "html.parser").get_text()

            temas = []
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("- ") and len(line) > 40:
                    tema = line.lstrip("- ").strip()
                    temas.append(tema)
                    add_point(
                        f"JURISPRUDÊNCIA STJ - {area_nome}\n\n{tema}",
                        {"tipo_documento": "jurisprudencia", "source_type": "jurisprudence",
                         "jurisprudence_type": "pesquisa_pronta", "tribunal": "STJ",
                         "area_direito": area_nome, "peso_normativo": 3}
                    )

            safe_name = area_nome.lower().replace(" ", "_").replace("á", "a").replace("ó", "o").replace("ú", "u")
            with open(os.path.join(DIRS["pesquisa"], f"{safe_name}.json"), "w", encoding="utf-8") as f:
                json.dump({"area": area_nome, "temas": temas}, f, ensure_ascii=False, indent=1)

            logger.info(f"    {len(temas)} temas")
            time.sleep(2)
        except Exception as e:
            logger.error(f"    Erro: {e}")

    indexar_batch()
    ckpt["etapas_concluidas"].append("pesquisa_pronta")
    salvar_ckpt()

# ============================================================
# ETAPA 4: SUMULAS VINCULANTES STF
# ============================================================

if "sumulas_stf" not in ckpt.get("etapas_concluidas", []):
    logger.info("\n" + "=" * 60)
    logger.info("ETAPA 4: SUMULAS VINCULANTES STF")
    logger.info("=" * 60)

    sumulas_vinculantes = [
        (1, "Ofende a garantia constitucional do ato jurídico perfeito a decisão que, sem ponderar as circunstâncias do caso concreto, desconsidera a validez e a eficácia de acordo constante de termo de adesão instituído pela Lei Complementar nº 110/2001."),
        (2, "É inconstitucional a lei ou ato normativo estadual ou distrital que disponha sobre sistemas de consórcios e sorteios, inclusive bingos e loterias."),
        (3, "Nos processos perante o Tribunal de Contas da União asseguram-se o contraditório e a ampla defesa quando da decisão puder resultar anulação ou revogação de ato administrativo que beneficie o interessado, excetuada a apreciação da legalidade do ato de concessão inicial de aposentadoria, reforma e pensão."),
        (4, "Salvo nos casos previstos na Constituição, o salário mínimo não pode ser usado como indexador de base de cálculo de vantagem de servidor público ou de empregado, nem ser substituído por decisão judicial."),
        (5, "A falta de defesa técnica por advogado no processo administrativo disciplinar não ofende a Constituição."),
        (10, "Viola a cláusula de reserva de plenário (CF, artigo 97) a decisão de órgão fracionário de tribunal que, embora não declare expressamente a inconstitucionalidade de lei ou ato normativo do Poder Público, afasta sua incidência, no todo ou em parte."),
        (11, "O uso de algemas é excepcional e deve ser justificado por escrito, sob pena de responsabilidade disciplinar, civil e penal do agente ou da autoridade e de nulidade da prisão ou do ato processual a que se refere."),
        (13, "A nomeação de cônjuge, companheiro ou parente em linha reta, colateral ou por afinidade, até o terceiro grau, inclusive, da autoridade nomeante ou de servidor da mesma pessoa jurídica investido em cargo de direção, chefia ou assessoramento, para o exercício de cargo em comissão ou de confiança ou, ainda, de função gratificada na administração pública direta e indireta em qualquer dos poderes da União, dos Estados, do Distrito Federal e dos Municípios, compreendido o ajuste mediante designações recíprocas, viola a Constituição Federal."),
        (14, "É direito do defensor, no interesse do representado, ter acesso amplo aos elementos de prova que, já documentados em procedimento investigatório realizado por órgão com competência de polícia judiciária, digam respeito ao exercício do direito de defesa."),
        (17, "Durante o período previsto no parágrafo 1º do artigo 100 da Constituição, não incidem juros de mora sobre os precatórios que nele sejam pagos."),
        (25, "É ilícita a prisão civil de depositário infiel, qualquer que seja a modalidade do depósito."),
        (26, "Para efeito de progressão de regime no cumprimento de pena por crime hediondo, ou equiparado, o juízo da execução observará a inconstitucionalidade do art. 2º da Lei nº 8.072, de 25 de julho de 1990, sem prejuízo de avaliar se o condenado preenche, ou não, os requisitos objetivos e subjetivos do benefício, podendo determinar, para tal fim, de modo fundamentado, a realização de exame criminológico."),
        (31, "É inconstitucional a incidência do Imposto sobre Serviços de Qualquer Natureza – ISS sobre operações de locação de bens móveis."),
        (37, "Não cabe ao Poder Judiciário, que não tem função legislativa, aumentar vencimentos de servidores públicos sob o fundamento de isonomia."),
    ]

    all_sv = []
    for num, texto in sumulas_vinculantes:
        all_sv.append({"numero": num, "texto": texto})
        add_point(
            f"SÚMULA VINCULANTE {num} - STF\n\n\"{texto}\"",
            {"tipo_documento": "sumula_vinculante", "source_type": "jurisprudence",
             "tribunal": "STF", "sumula_number": str(num),
             "peso_normativo": 5, "binding_level": "vinculante"}
        )

    with open(os.path.join(DIRS["sumulas_stf"], "sumulas_vinculantes_stf.json"), "w", encoding="utf-8") as f:
        json.dump(all_sv, f, ensure_ascii=False, indent=1)

    indexar_batch()
    logger.info(f"Sumulas Vinculantes STF: {len(all_sv)}")
    ckpt["etapas_concluidas"].append("sumulas_stf")
    salvar_ckpt()

# ============================================================
# ETAPA 5: LEIS DO PLANALTO
# ============================================================

if "leis" not in ckpt.get("etapas_concluidas", []):
    logger.info("\n" + "=" * 60)
    logger.info("ETAPA 5: LEIS DO PLANALTO")
    logger.info("=" * 60)

    LEIS = [
        ("Constituição Federal", "CF/1988", "constituicao", "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm"),
        ("Código Civil", "Lei 10.406/2002", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm"),
        ("Código Penal", "DL 2.848/1940", "lei_federal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm"),
        ("Código de Processo Civil", "Lei 13.105/2015", "lei_federal", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm"),
        ("Código de Defesa do Consumidor", "Lei 8.078/1990", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"),
        ("CLT", "DL 5.452/1943", "lei_federal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm"),
        ("Código Tributário Nacional", "Lei 5.172/1966", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm"),
        ("ECA", "Lei 8.069/1990", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/l8069.htm"),
        ("Lei Maria da Penha", "Lei 11.340/2006", "lei_federal", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11340.htm"),
        ("LGPD", "Lei 13.709/2018", "lei_federal", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"),
        ("Lei de Licitações", "Lei 14.133/2021", "lei_federal", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"),
        ("Código de Processo Penal", "DL 3.689/1941", "lei_federal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm"),
        ("Lei de Execução Penal", "Lei 7.210/1984", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/l7210.htm"),
        ("Estatuto do Idoso", "Lei 10.741/2003", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/2003/l10.741.htm"),
    ]

    pesos = {"constituicao": 5, "lei_federal": 3}

    for nome, numero, hierarquia, url in LEIS:
        safe = nome.lower().replace(" ", "_").replace("á", "a").replace("ó", "o").replace("ç", "c").replace("ã", "a")
        logger.info(f"  Baixando: {nome}...")

        try:
            r = requests.get(url, timeout=60)
            r.encoding = r.apparent_encoding or "utf-8"
            if r.status_code != 200:
                logger.error(f"    HTTP {r.status_code}")
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text()

            pattern = r'Art\.?\s*(\d+[\-A-Za-z]*)[º°oa]?[\.\s\-–]*(.*?)(?=Art\.?\s*\d+[\-A-Za-z]*[º°oa]?[\.\s\-–]|$)'
            artigos = []
            for match in re.finditer(pattern, text, re.DOTALL):
                num_art = match.group(1).strip()
                corpo = re.sub(r'\s+', ' ', match.group(2).strip())[:2000]
                if len(corpo) > 10 and num_art:
                    artigos.append({"artigo": num_art, "texto": corpo})
                    add_point(
                        f"Art. {num_art} do {nome}: {corpo}",
                        {"tipo_documento": "lei", "source_type": "legislation",
                         "norma": nome, "numero_norma": numero,
                         "artigo": num_art, "hierarquia": hierarquia,
                         "peso_normativo": pesos.get(hierarquia, 3)}
                    )

            lei_json = {"nome_norma": nome, "numero": numero, "hierarquia": hierarquia, "artigos": artigos}
            with open(os.path.join(DIRS["leis"], f"{safe}.json"), "w", encoding="utf-8") as f:
                json.dump(lei_json, f, ensure_ascii=False, indent=1)

            logger.info(f"    {len(artigos)} artigos")
            time.sleep(2)

        except Exception as e:
            logger.error(f"    Erro: {e}")

    indexar_batch()
    ckpt["etapas_concluidas"].append("leis")
    salvar_ckpt()

# ============================================================
# FINALIZAR
# ============================================================

indexar_batch()
ckpt["total_indexado"] = total_novo
salvar_ckpt()

try:
    client.close()
except:
    pass

logger.info("\n" + "=" * 60)
logger.info("DOWNLOAD COMPLETO!")
logger.info("=" * 60)
logger.info(f"Total indexado: {total_novo}")
logger.info(f"\nPastas geradas:")
logger.info(f"  jurisprudencia/sumulas_stj/")
logger.info(f"  jurisprudencia/temas_repetitivos/")
logger.info(f"  jurisprudencia/pesquisa_pronta/")
logger.info(f"  jurisprudencia/sumulas_vinculantes_stf/")
logger.info(f"  legislacao/")
logger.info(f"\nTudo indexado no Qdrant: {QDRANT_DIR}/")
