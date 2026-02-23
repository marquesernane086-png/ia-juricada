"""
JuristaAI - Script de Indexacao Local (Producao)
=================================================
Processa livros juridicos (PDF/EPUB) e cria indice vetorial para o JuristaAI.

Uso:
    python indexar_acervo.py

Compativel com o servidor JuristaAI - gera pasta "indice" para importacao.
"""

import os
import sys
import json
import hashlib
import re
import time
import logging
from pathlib import Path
from datetime import datetime

try:
    import fitz  # PyMuPDF
    from ebooklib import epub
    from bs4 import BeautifulSoup
    from llama_index.core import Document, VectorStoreIndex, StorageContext, Settings
    from llama_index.core import load_index_from_storage
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
except ImportError as e:
    print(f"\nDependencia faltando: {e}")
    print("Execute: pip install -r requirements_local.txt")
    sys.exit(1)

# ============================================================
# CONFIGURACAO
# ============================================================

PASTA_LIVROS = r"C:\Users\joaop\OneDrive\IA DIREITO"
PASTA_INDICE = "indice"
ARQUIVO_CONTROLE = "controle_index.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("JuristaAI")

# Configurar embedding model
logger.info("Carregando modelo de embeddings...")
Settings.embed_model = HuggingFaceEmbedding(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
logger.info("Modelo carregado!")

# ============================================================
# CONTROLE DE INDEXACAO
# ============================================================

if os.path.exists(ARQUIVO_CONTROLE):
    with open(ARQUIVO_CONTROLE, "r", encoding="utf-8") as f:
        controle = json.load(f)
else:
    controle = {}


def salvar_controle():
    with open(ARQUIVO_CONTROLE, "w", encoding="utf-8") as f:
        json.dump(controle, f, indent=2, ensure_ascii=False)


def hash_arquivo(path):
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


# ============================================================
# LEITURA PDF
# ============================================================

def ler_pdf(path):
    """Retorna texto completo E lista de paginas com numero."""
    texto = ""
    paginas = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            page_text = page.get_text()
            if page_text.strip():
                paginas.append({"pagina": i + 1, "texto": page_text.strip()})
                texto += page_text
    return texto, paginas


# ============================================================
# LEITURA EPUB
# ============================================================

def ler_epub(path):
    """Retorna texto completo E lista de capitulos com numero."""
    texto = ""
    paginas = []
    book = epub.read_epub(path, options={'ignore_ncx': True})
    cap_num = 0
    for item in book.get_items():
        if item.get_type() == 9:
            soup = BeautifulSoup(item.get_content(), "html.parser")
            page_text = soup.get_text()
            if page_text.strip() and len(page_text.strip()) > 50:
                cap_num += 1
                paginas.append({"pagina": cap_num, "texto": page_text.strip()})
                texto += page_text
    return texto, paginas


# ============================================================
# EXTRACAO DE METADADOS
# ============================================================

def extrair_ano(nome, texto=""):
    """Extrai ano do nome do arquivo ou do texto."""
    # Primeiro tenta no nome do arquivo
    match = re.search(r"(19|20)\d{2}", nome)
    if match:
        return int(match.group())

    # Depois tenta no texto (primeiros 3000 chars)
    amostra = texto[:3000]
    patterns = [
        r'(?:edicao|ed\.)\s*(?:de\s+)?((?:19|20)\d{2})',
        r'(?:copyright|©)\s*((?:19|20)\d{2})',
        r'((?:19|20)\d{2})\s*(?:by|por)',
    ]
    for pattern in patterns:
        match = re.search(pattern, amostra, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return 0


def extrair_autor(nome_arquivo, texto=""):
    """Tenta extrair o autor do nome do arquivo ou do texto."""
    nome = Path(nome_arquivo).stem

    # Padrao: "Autor - Titulo" ou "Titulo - Autor"
    partes = re.split(r'\s*[-–—]\s*', nome, maxsplit=1)
    if len(partes) == 2:
        # Heuristica: se a primeira parte tem menos de 40 chars, provavelmente e o autor
        if len(partes[0]) < 40:
            return partes[0].strip()

    # Tenta extrair do texto (primeiras paginas)
    amostra = texto[:2000]
    patterns = [
        r'(?:autor|by|por)[:\s]+([A-Z][a-zA-Z\s\.]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, amostra)
        if match:
            return match.group(1).strip()[:60]

    return ""


def extrair_edicao(nome_arquivo, texto=""):
    """Tenta extrair edicao."""
    amostra = (nome_arquivo + " " + texto[:2000])
    patterns = [
        r'(\d+)[aª°]?\s*(?:edicao|edicão|ed\.)',
        r'(?:edicao|edicão|ed\.)\s*(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, amostra, re.IGNORECASE)
        if match:
            return f"{match.group(1)}a edicao"
    return ""


def detectar_materia(nome, texto, caminho):
    """Detecta a materia juridica automaticamente."""
    base = (nome + " " + caminho + " " + texto[:3000]).lower()

    materias = {
        "Direito Civil": [
            "civil", "obrigacoes", "obrigações", "contratos", "responsabilidade civil",
            "familia", "família", "sucessoes", "sucessões", "direitos reais",
            "pessoa natural", "pessoa juridica", "negocio juridico"
        ],
        "Direito Penal": [
            "penal", "crime", "pena", "criminologia", "delito",
            "tipicidade", "antijuridicidade", "culpabilidade"
        ],
        "Processo Civil": [
            "processo civil", "processual civil", "cpc", "codigo de processo civil",
            "tutela provisoria", "recursos civeis"
        ],
        "Processo Penal": [
            "processo penal", "processual penal", "cpp",
            "inquerito policial", "acao penal"
        ],
        "Direito Constitucional": [
            "constituicao", "constitucional", "direitos fundamentais",
            "controle de constitucionalidade", "poder constituinte",
            "direitos humanos"
        ],
        "Direito Administrativo": [
            "administrativo", "licitacao", "licitação", "servidor publico",
            "ato administrativo", "poder de policia", "concessao"
        ],
        "Direito Tributario": [
            "tributario", "tributário", "imposto", "tributo", "icms",
            "contribuicao", "taxa", "fato gerador"
        ],
        "Direito do Trabalho": [
            "trabalho", "trabalhista", "clt", "empregado", "empregador",
            "rescisao", "ferias", "salario"
        ],
        "Direito Empresarial": [
            "empresarial", "comercial", "sociedade", "falencia",
            "recuperacao judicial", "titulos de credito"
        ],
        "Direito Ambiental": [
            "ambiental", "meio ambiente", "licenciamento",
            "dano ambiental", "sustentabilidade"
        ],
        "Direito do Consumidor": [
            "consumidor", "cdc", "relacao de consumo",
            "praticas abusivas", "recall"
        ],
        "Direito Internacional": [
            "internacional", "tratado", "convencao",
            "direito comunitario", "extradicao"
        ],
        "Direito Urbanistico": [
            "estatuto da cidade", "urbanistico", "urbanístico",
            "zoneamento", "plano diretor"
        ],
    }

    for materia, palavras in materias.items():
        if any(p in base for p in palavras):
            return materia

    return "Geral"


# ============================================================
# PROCESSAMENTO
# ============================================================

documentos = []
livros_processados = 0
livros_pulados = 0
livros_erro = 0
start_time = time.time()

logger.info(f"Buscando livros em: {PASTA_LIVROS}")

total_arquivos = 0
for raiz, _, arquivos in os.walk(PASTA_LIVROS):
    for arquivo in arquivos:
        ext = arquivo.lower()
        if ext.endswith(".pdf") or ext.endswith(".epub"):
            total_arquivos += 1

logger.info(f"Encontrados: {total_arquivos} livros")
logger.info("=" * 60)

contador = 0
for raiz, _, arquivos in os.walk(PASTA_LIVROS):
    for arquivo in arquivos:
        ext = arquivo.lower()
        if not (ext.endswith(".pdf") or ext.endswith(".epub")):
            continue

        contador += 1
        caminho = os.path.join(raiz, arquivo)
        file_hash = hash_arquivo(caminho)

        if file_hash in controle:
            livros_pulados += 1
            continue

        logger.info(f"[{contador}/{total_arquivos}] {arquivo}")

        try:
            if ext.endswith(".pdf"):
                texto, paginas = ler_pdf(caminho)
            else:
                texto, paginas = ler_epub(caminho)

            if len(texto.strip()) < 500:
                logger.warning("  Texto muito pequeno - ignorado")
                livros_erro += 1
                continue

            ano = extrair_ano(arquivo, texto)
            autor = extrair_autor(arquivo, texto)
            edicao = extrair_edicao(arquivo, texto)
            materia = detectar_materia(arquivo, texto, raiz)

            logger.info(f"  Autor: {autor or '?'}")
            logger.info(f"  Ano: {ano or '?'} | Materia: {materia} | Paginas: {len(paginas)}")
            if edicao:
                logger.info(f"  Edicao: {edicao}")

            # Criar um Document POR PAGINA para preservar numero da pagina
            for pg in paginas:
                if len(pg["texto"].strip()) < 50:
                    continue
                doc = Document(
                    text=pg["texto"],
                    metadata={
                        "arquivo": arquivo,
                        "caminho": raiz,
                        "ano": ano,
                        "author": autor,
                        "autor": autor,
                        "title": Path(arquivo).stem,
                        "edicao": edicao,
                        "materia": materia,
                        "legal_subject": materia,
                        "hash": file_hash,
                        "page": pg["pagina"],
                        "pagina": pg["pagina"],
                    },
                )
                documentos.append(doc)

            controle[file_hash] = {
                "arquivo": arquivo,
                "autor": autor,
                "ano": ano,
                "edicao": edicao,
                "materia": materia,
                "paginas": len(paginas),
            }

            salvar_controle()
            livros_processados += 1

            # Indexar em lotes de 50 documentos (paginas) para nao perder progresso
            if len(documentos) >= 50:
                logger.info(f"  Indexando lote de {len(documentos)} paginas...")
                if os.path.exists(PASTA_INDICE):
                    storage = StorageContext.from_defaults(persist_dir=PASTA_INDICE)
                    index = load_index_from_storage(storage)
                    for d in documentos:
                        index.insert(d)
                else:
                    index = VectorStoreIndex.from_documents(documentos)
                index.storage_context.persist(persist_dir=PASTA_INDICE)
                documentos = []
                logger.info("  Lote indexado e salvo!")

        except Exception as e:
            logger.error(f"  Erro: {e}")
            livros_erro += 1
            continue

# ============================================================
# INDEXACAO FINAL
# ============================================================

if documentos:
    logger.info(f"Indexando lote final de {len(documentos)} documentos...")
    if os.path.exists(PASTA_INDICE):
        storage = StorageContext.from_defaults(persist_dir=PASTA_INDICE)
        index = load_index_from_storage(storage)
        for d in documentos:
            index.insert(d)
    else:
        index = VectorStoreIndex.from_documents(documentos)
    index.storage_context.persist(persist_dir=PASTA_INDICE)
    logger.info("Indexacao concluida!")

# ============================================================
# RELATORIO FINAL
# ============================================================

elapsed = time.time() - start_time
elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))

logger.info("")
logger.info("=" * 60)
logger.info("INDEXACAO CONCLUIDA")
logger.info("=" * 60)
logger.info(f"Livros processados: {livros_processados}")
logger.info(f"Livros pulados (ja indexados): {livros_pulados}")
logger.info(f"Livros com erro: {livros_erro}")
logger.info(f"Tempo: {elapsed_str}")
logger.info("")
logger.info(f"Arquivos gerados:")
logger.info(f"  {PASTA_INDICE}/        - indice vetorial (para o servidor)")
logger.info(f"  {ARQUIVO_CONTROLE}  - controle de indexacao")
logger.info("")
logger.info("PROXIMO PASSO:")
logger.info(f"  1. Compacte a pasta '{PASTA_INDICE}' e '{ARQUIVO_CONTROLE}' em um ZIP")
logger.info(f"  2. Importe pelo botao 'Importar ZIP' no JuristaAI")

if livros_erro > 0:
    logger.info(f"")
    logger.info(f"{livros_erro} livros tiveram erro.")
