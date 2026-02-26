"""JuristaAI — Baixar Toda Jurisprudência e Legislação

APENAS BAIXA E ORGANIZA EM PASTAS. NÃO INDEXA NADA.

Uso:
    python baixar_tudo.py

Estrutura gerada:
    jurisprudencia/
        sumulas_stj/
        temas_repetitivos/
        pesquisa_pronta/
        sumulas_vinculantes_stf/
    legislacao/
        constituicao_federal.json
        codigo_civil.json
        ...
"""

import os
import re
import json
import time
import logging

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
logger = logging.getLogger("Download")

CHECKPOINT = "controle_download.json"

DIRS = {
    "sumulas_stj": "jurisprudencia/sumulas_stj",
    "temas": "jurisprudencia/temas_repetitivos",
    "pesquisa": "jurisprudencia/pesquisa_pronta",
    "sumulas_stf": "jurisprudencia/sumulas_vinculantes_stf",
    "leis": "legislacao",
}
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

if os.path.exists(CHECKPOINT):
    with open(CHECKPOINT, "r", encoding="utf-8") as f:
        ckpt = json.load(f)
else:
    ckpt = {"etapas": []}

def salvar():
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, indent=2, ensure_ascii=False)

# ============================================================
# 1. SUMULAS STJ
# ============================================================
if "sumulas_stj" not in ckpt["etapas"]:
    logger.info("=" * 50)
    logger.info("1/5 SUMULAS STJ")
    try:
        import fitz
        r = requests.get("https://scon.stj.jus.br/docs_internet/VerbetesSTJ.pdf", timeout=60)
        pdf_path = os.path.join(DIRS["sumulas_stj"], "VerbetesSTJ.pdf")
        with open(pdf_path, "wb") as f:
            f.write(r.content)

        doc = fitz.open(pdf_path)
        text = "".join(p.get_text() for p in doc)
        doc.close()

        sumulas = []
        for num, txt in re.findall(r'SÚMULA\s+(\d+)\s+(.*?)(?=SÚMULA\s+\d+|$)', text, re.DOTALL):
            txt = re.sub(r'\s+', ' ', txt).strip()
            if len(txt) > 20:
                sumulas.append({"numero": int(num), "texto": txt})
        sumulas.sort(key=lambda x: x["numero"])

        with open(os.path.join(DIRS["sumulas_stj"], "sumulas_stj.json"), "w", encoding="utf-8") as f:
            json.dump(sumulas, f, ensure_ascii=False, indent=1)
        logger.info(f"  {len(sumulas)} sumulas salvas")
        ckpt["etapas"].append("sumulas_stj")
        salvar()
    except Exception as e:
        logger.error(f"  Erro: {e}")

# ============================================================
# 2. TEMAS REPETITIVOS STJ
# ============================================================
if "temas" not in ckpt["etapas"]:
    logger.info("=" * 50)
    logger.info("2/5 TEMAS REPETITIVOS STJ")
    all_temas = []
    for page in range(29):
        offset = page * 50 + 1
        logger.info(f"  Pagina {page+1}/29")
        try:
            r = requests.get(f"https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp?novaConsulta=true&tipo_pesquisa=T&situacao=JULGADO&l=50&i={offset}", timeout=30)
            text = BeautifulSoup(r.text, "html.parser").get_text()
            for block in re.split(r'Documento \d+', text):
                m = re.search(r'Tema Repetitivo\s*(\d+)', block)
                if not m:
                    continue
                num = int(m.group(1))
                tese = ""
                tm = re.search(r'Tese Firmada\s*(.*?)(?=Anota|Delimita|Informa|Repercuss|Entendimento|Refer|$)', block, re.DOTALL)
                if tm:
                    tese = re.sub(r'\s+', ' ', tm.group(1)).strip()
                if not tese or len(tese) < 20:
                    continue
                area = "Geral"
                am = re.search(r'Ramo do direito\s*(.*?)(?=Quest|$)', block)
                if am:
                    area = re.sub(r'\s+', ' ', am.group(1)).strip()
                proc = ""
                pm = re.search(r'(REsp|AREsp|EREsp|CC)\s*(\d+/[A-Z]{2})', block)
                if pm:
                    proc = f"{pm.group(1)} {pm.group(2)}"
                rel = ""
                rm = re.search(r'Relator\s*([A-Z][A-Z\s\.]+?)(?=Embargo|Afeta|$)', block)
                if rm:
                    rel = rm.group(1).strip()[:60]
                all_temas.append({"tema": num, "tese": tese, "area": area, "processo": proc, "relator": rel})
            time.sleep(2)
        except Exception as e:
            logger.error(f"  Erro pagina {page+1}: {e}")
            time.sleep(5)

    with open(os.path.join(DIRS["temas"], "temas_stj.json"), "w", encoding="utf-8") as f:
        json.dump(all_temas, f, ensure_ascii=False, indent=1)
    logger.info(f"  {len(all_temas)} temas salvos")
    ckpt["etapas"].append("temas")
    salvar()

# ============================================================
# 3. PESQUISA PRONTA STJ
# ============================================================
if "pesquisa" not in ckpt["etapas"]:
    logger.info("=" * 50)
    logger.info("3/5 PESQUISA PRONTA STJ")
    AREAS = {
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
    for area, code in AREAS.items():
        logger.info(f"  {area}")
        try:
            r = requests.get(f"https://scon.stj.jus.br/SCON/pesquisa_pronta/toc.jsp?livre=%27{code}%27.mat.", timeout=30)
            text = BeautifulSoup(r.text, "html.parser").get_text()
            temas = [l.lstrip("- ").strip() for l in text.split("\n") if l.strip().startswith("- ") and len(l) > 40]
            safe = area.lower().replace(" ", "_").replace("á", "a").replace("ó", "o").replace("ú", "u").replace("é", "e")
            with open(os.path.join(DIRS["pesquisa"], f"{safe}.json"), "w", encoding="utf-8") as f:
                json.dump({"area": area, "temas": temas}, f, ensure_ascii=False, indent=1)
            logger.info(f"    {len(temas)} temas")
            time.sleep(2)
        except Exception as e:
            logger.error(f"    Erro: {e}")
    ckpt["etapas"].append("pesquisa")
    salvar()

# ============================================================
# 4. SUMULAS VINCULANTES STF
# ============================================================
if "sumulas_stf" not in ckpt["etapas"]:
    logger.info("=" * 50)
    logger.info("4/5 SUMULAS VINCULANTES STF")
    sv = [
        (1, "Ofende a garantia constitucional do ato jurídico perfeito a decisão que, sem ponderar as circunstâncias do caso concreto, desconsidera a validez e a eficácia de acordo constante de termo de adesão instituído pela Lei Complementar nº 110/2001."),
        (2, "É inconstitucional a lei ou ato normativo estadual ou distrital que disponha sobre sistemas de consórcios e sorteios, inclusive bingos e loterias."),
        (3, "Nos processos perante o Tribunal de Contas da União asseguram-se o contraditório e a ampla defesa quando da decisão puder resultar anulação ou revogação de ato administrativo que beneficie o interessado."),
        (4, "Salvo nos casos previstos na Constituição, o salário mínimo não pode ser usado como indexador de base de cálculo de vantagem de servidor público ou de empregado."),
        (5, "A falta de defesa técnica por advogado no processo administrativo disciplinar não ofende a Constituição."),
        (10, "Viola a cláusula de reserva de plenário (CF, artigo 97) a decisão de órgão fracionário de tribunal que afasta a incidência de lei ou ato normativo do Poder Público."),
        (11, "O uso de algemas é excepcional e deve ser justificado por escrito, sob pena de responsabilidade disciplinar, civil e penal do agente."),
        (13, "A nomeação de cônjuge, companheiro ou parente em linha reta, colateral ou por afinidade, até o terceiro grau, para o exercício de cargo em comissão ou de confiança, viola a Constituição Federal."),
        (14, "É direito do defensor ter acesso amplo aos elementos de prova já documentados em procedimento investigatório."),
        (25, "É ilícita a prisão civil de depositário infiel, qualquer que seja a modalidade do depósito."),
        (26, "Para efeito de progressão de regime no cumprimento de pena por crime hediondo, o juízo da execução observará a inconstitucionalidade do art. 2º da Lei nº 8.072/1990."),
        (31, "É inconstitucional a incidência do ISS sobre operações de locação de bens móveis."),
        (37, "Não cabe ao Poder Judiciário aumentar vencimentos de servidores públicos sob o fundamento de isonomia."),
    ]
    with open(os.path.join(DIRS["sumulas_stf"], "sumulas_vinculantes_stf.json"), "w", encoding="utf-8") as f:
        json.dump([{"numero": n, "texto": t} for n, t in sv], f, ensure_ascii=False, indent=1)
    logger.info(f"  {len(sv)} sumulas salvas")
    ckpt["etapas"].append("sumulas_stf")
    salvar()

# ============================================================
# 5. LEIS DO PLANALTO
# ============================================================
if "leis" not in ckpt["etapas"]:
    logger.info("=" * 50)
    logger.info("5/5 LEGISLACAO")
    LEIS = [
        ("Constituição Federal", "CF/1988", "constituicao", "https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm"),
        ("Código Civil", "Lei 10.406/2002", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm"),
        ("Código Penal", "DL 2.848/1940", "lei_federal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm"),
        ("CPC", "Lei 13.105/2015", "lei_federal", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm"),
        ("CDC", "Lei 8.078/1990", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"),
        ("CLT", "DL 5.452/1943", "lei_federal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm"),
        ("CTN", "Lei 5.172/1966", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm"),
        ("ECA", "Lei 8.069/1990", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/l8069.htm"),
        ("Lei Maria da Penha", "Lei 11.340/2006", "lei_federal", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11340.htm"),
        ("LGPD", "Lei 13.709/2018", "lei_federal", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"),
        ("Lei Licitações", "Lei 14.133/2021", "lei_federal", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"),
        ("CPP", "DL 3.689/1941", "lei_federal", "https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm"),
        ("LEP", "Lei 7.210/1984", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/l7210.htm"),
        ("Estatuto Idoso", "Lei 10.741/2003", "lei_federal", "https://www.planalto.gov.br/ccivil_03/leis/2003/l10.741.htm"),
    ]
    for nome, numero, hier, url in LEIS:
        safe = nome.lower().replace(" ", "_").replace("á", "a").replace("ó", "o").replace("ç", "c").replace("ã", "a").replace("ú", "u").replace("é", "e")
        logger.info(f"  {nome}...")
        try:
            r = requests.get(url, timeout=60)
            r.encoding = r.apparent_encoding or "utf-8"
            text = BeautifulSoup(r.text, "html.parser").get_text()
            artigos = []
            for m in re.finditer(r'Art\.?\s*(\d+[\-A-Za-z]*)[º°oa]?[\.\s\-–]*(.*?)(?=Art\.?\s*\d+[\-A-Za-z]*[º°oa]?[\.\s\-–]|$)', text, re.DOTALL):
                num = m.group(1).strip()
                corpo = re.sub(r'\s+', ' ', m.group(2).strip())[:2000]
                if len(corpo) > 10:
                    artigos.append({"artigo": num, "texto": corpo})
            with open(os.path.join(DIRS["leis"], f"{safe}.json"), "w", encoding="utf-8") as f:
                json.dump({"nome": nome, "numero": numero, "hierarquia": hier, "artigos": artigos}, f, ensure_ascii=False, indent=1)
            logger.info(f"    {len(artigos)} artigos")
            time.sleep(2)
        except Exception as e:
            logger.error(f"    Erro: {e}")
    ckpt["etapas"].append("leis")
    salvar()

# ============================================================
logger.info("\n" + "=" * 50)
logger.info("TUDO BAIXADO!")
logger.info("=" * 50)
logger.info("Pastas:")
for d in DIRS.values():
    count = len([f for f in os.listdir(d) if f.endswith(".json")])
    logger.info(f"  {d}/ ({count} arquivos)")
logger.info("\nPara indexar depois: python indexar_leis.py / python indexar_jurisprudencia.py")
