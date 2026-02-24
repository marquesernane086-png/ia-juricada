"""
JuristaAI - Script de Indexacao Local (DEFINITIVO)
====================================================
Processa livros juridicos (PDF/EPUB) e cria indice vetorial para o JuristaAI.

Recursos:
- Extrai autor/titulo dos metadados internos do PDF
- Chunking inteligente (~1000 chars) com separadores juridicos
- Preserva numero da pagina em cada chunk
- Detecta capitulos automaticamente
- Checkpoint: nao repete arquivos ja indexados
- Lotes incrementais: salva progresso a cada livro

Uso:
    python indexar_acervo.py
"""

import os
import sys
import json
import hashlib
import re
import time
import logging
import uuid
from pathlib import Path
from datetime import datetime

try:
    import fitz  # PyMuPDF
    from ebooklib import epub
    from bs4 import BeautifulSoup
    from llama_index.core import Document, VectorStoreIndex, StorageContext, Settings
    from llama_index.core import load_index_from_storage
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from legal_source_classifier import classificar_fonte
except ImportError as e:
    print(f"\nDependencia faltando: {e}")
    print("Execute: pip install -r requirements_local.txt")
    sys.exit(1)

# ============================================================
# CONFIGURACAO - AJUSTE AQUI
# ============================================================

PASTA_LIVROS = r"C:\Users\joaop\OneDrive\Faculdade UNESA\LIVROS"
PASTA_INDICE = "indice"
ARQUIVO_CONTROLE = "controle_index.json"
CHUNK_SIZE = 1024        # tamanho ideal do chunk em caracteres
CHUNK_OVERLAP = 200      # sobreposicao entre chunks
LOTE_SALVAR = 200        # salvar indice a cada N chunks

# ============================================================
# SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("indexacao.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("JuristaAI")

logger.info("Carregando modelo de embeddings (primeira vez baixa ~500MB)...")
Settings.embed_model = HuggingFaceEmbedding(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
logger.info("Modelo carregado!")

# Chunker com separadores juridicos
SEPARADORES_JURIDICOS = [
    "\n\nCAPÍTULO", "\nCAPÍTULO", "\n\nCAPITULO", "\nCAPITULO",
    "\n\nSEÇÃO", "\nSEÇÃO", "\n\nSECAO", "\nSECAO",
    "\n\nTÍTULO", "\nTÍTULO", "\n\nTITULO", "\nTITULO",
    "\n\nArt.", "\nArt.",
    "\n\n§", "\n§",
    "\n\nSumário:", "\nSumário:",
    "\n\n", "\n",
    ". ", " ",
]

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
            bloco = f.read(8192)
            if not bloco:
                break
            sha.update(bloco)
    return sha.hexdigest()


def _doctrine_hash(text):
    """Short hash for doctrine graph IDs."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]



# ============================================================
# EXTRACAO DE TEXTO - PDF
# ============================================================

def ler_pdf(path):
    """Extrai texto pagina por pagina + metadados internos do PDF."""
    doc = fitz.open(path)
    meta_pdf = doc.metadata or {}

    # Metadados internos do PDF
    autor_pdf = (meta_pdf.get("author") or "").strip()
    titulo_pdf = (meta_pdf.get("title") or "").strip()

    paginas = []
    capitulo_atual = ""

    for i in range(len(doc)):
        page = doc[i]
        texto = page.get_text("text")
        if not texto or len(texto.strip()) < 30:
            continue

        # Detectar capitulo
        cap = detectar_capitulo(texto)
        if cap:
            capitulo_atual = cap

        paginas.append({
            "pagina": i + 1,
            "texto": texto.strip(),
            "capitulo": capitulo_atual,
        })

    total_paginas = len(doc)
    doc.close()

    # Texto completo (para detectar materia/ano)
    texto_completo = "\n".join(p["texto"] for p in paginas[:20])  # primeiras 20 pags

    return paginas, {
        "autor_pdf": autor_pdf,
        "titulo_pdf": titulo_pdf,
        "total_paginas": total_paginas,
        "texto_amostra": texto_completo,
    }


# ============================================================
# EXTRACAO DE TEXTO - EPUB
# ============================================================

def ler_epub(path):
    """Extrai texto capitulo por capitulo + metadados do EPUB."""
    book = epub.read_epub(path, options={'ignore_ncx': True})

    # Metadados
    autor_epub = ""
    titulo_epub = ""

    title_meta = book.get_metadata('DC', 'title')
    if title_meta and title_meta[0]:
        titulo_epub = title_meta[0][0] or ""

    author_meta = book.get_metadata('DC', 'creator')
    if author_meta and author_meta[0]:
        autor_epub = author_meta[0][0] or ""

    paginas = []
    capitulo_atual = ""
    cap_num = 0

    for item in book.get_items():
        if item.get_type() == 9:
            soup = BeautifulSoup(item.get_content(), "html.parser")
            texto = soup.get_text(separator="\n", strip=True)
            if not texto or len(texto.strip()) < 50:
                continue

            cap_num += 1
            cap = detectar_capitulo(texto)
            if cap:
                capitulo_atual = cap

            paginas.append({
                "pagina": cap_num,
                "texto": texto.strip(),
                "capitulo": capitulo_atual,
            })

    texto_completo = "\n".join(p["texto"] for p in paginas[:10])

    return paginas, {
        "autor_pdf": autor_epub,
        "titulo_pdf": titulo_epub,
        "total_paginas": cap_num,
        "texto_amostra": texto_completo,
    }


# ============================================================
# DETECCAO DE CAPITULO
# ============================================================

def detectar_capitulo(texto):
    """Detecta titulo de capitulo nas primeiras linhas do texto."""
    primeiras_linhas = texto[:500]
    patterns = [
        r'(CAP[IÍ]TULO\s+[IVXLCDM\d]+[\s\.\-–:]*[^\n]{0,80})',
        r'(Cap[ií]tulo\s+[IVXLCDM\d]+[\s\.\-–:]*[^\n]{0,80})',
        r'(SE[CÇ][AÃ]O\s+[IVXLCDM\d]+[\s\.\-–:]*[^\n]{0,80})',
        r'(T[IÍ]TULO\s+[IVXLCDM\d]+[\s\.\-–:]*[^\n]{0,80})',
        r'(PARTE\s+[IVXLCDM\d]+[\s\.\-–:]*[^\n]{0,80})',
        r'(LIVRO\s+[IVXLCDM\d]+[\s\.\-–:]*[^\n]{0,80})',
    ]
    for pattern in patterns:
        match = re.search(pattern, primeiras_linhas)
        if match:
            return match.group(1).strip()[:120]
    return ""


# ============================================================
# ISBN - EXTRACAO E BUSCA ONLINE
# ============================================================

def extrair_isbn(texto_amostra, texto_final=""):
    """Extrai ISBN do texto (primeiras e ultimas paginas)."""
    texto_busca = texto_amostra + "\n" + texto_final

    # ISBN-13: 978 ou 979 seguido de 10 digitos
    patterns = [
        r'ISBN[\s:\-]*(\d[\d\-\s]{11,16}\d)',
        r'ISBN[\s:\-]*(\d{3}[\-\s]?\d[\-\s]?\d{2,5}[\-\s]?\d{2,6}[\-\s]?\d)',
        r'(97[89][\-\s]?\d[\-\s]?\d{2,5}[\-\s]?\d{2,6}[\-\s]?\d)',
        r'(97[89]\d{10})',
    ]

    for pattern in patterns:
        match = re.search(pattern, texto_busca, re.IGNORECASE)
        if match:
            isbn = re.sub(r'[\s\-]', '', match.group(1))
            if len(isbn) == 13 and isbn.startswith(('978', '979')):
                return isbn
            elif len(isbn) == 10:
                return isbn

    return ""


# Cache para nao repetir consultas
_isbn_cache = {}


def buscar_isbn_online(isbn):
    """Busca metadados do livro pelo ISBN via APIs gratuitas."""
    if not isbn:
        return None

    if isbn in _isbn_cache:
        return _isbn_cache[isbn]

    resultado = None

    # 1. Google Books API (gratuita, sem chave)
    try:
        import requests
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if data.get("totalItems", 0) > 0:
                info = data["items"][0]["volumeInfo"]
                resultado = {
                    "titulo": info.get("title", ""),
                    "autor": ", ".join(info.get("authors", [])),
                    "ano": 0,
                    "editora": info.get("publisher", ""),
                    "isbn": isbn,
                    "fonte": "Google Books",
                }
                # Extrair ano
                pub_date = info.get("publishedDate", "")
                year_match = re.search(r'(\d{4})', pub_date)
                if year_match:
                    resultado["ano"] = int(year_match.group(1))

                logger.info(f"  ISBN {isbn} -> Google Books: {resultado['autor']} - {resultado['titulo']}")
    except Exception:
        pass

    # 2. Open Library (fallback)
    if not resultado:
        try:
            import requests
            url = f"https://openlibrary.org/search.json?isbn={isbn}&limit=1"
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if data.get("numFound", 0) > 0:
                    doc = data["docs"][0]
                    autores = doc.get("author_name", [])
                    resultado = {
                        "titulo": doc.get("title", ""),
                        "autor": ", ".join(autores) if autores else "",
                        "ano": doc.get("first_publish_year", 0),
                        "editora": ", ".join(doc.get("publisher", [])[:2]),
                        "isbn": isbn,
                        "fonte": "Open Library",
                    }
                    logger.info(f"  ISBN {isbn} -> Open Library: {resultado['autor']} - {resultado['titulo']}")
        except Exception:
            pass

    _isbn_cache[isbn] = resultado
    return resultado


# ============================================================
# EXTRACAO DE METADADOS
# ============================================================

def extrair_autor(nome_arquivo, meta_pdf, texto_amostra):
    """Extrai autor: 1) metadados PDF, 2) nome do arquivo, 3) texto."""
    # 1. Metadados internos do PDF
    autor = meta_pdf.get("autor_pdf", "")
    if autor and len(autor) > 2 and autor.lower() not in [
        "unknown", "admin", "user", "microsoft", "adobe",
        "scanner", "ocr", "calibre", "epublib",
    ]:
        return autor.strip()

    # 2. Nome do arquivo: "Autor - Titulo (Ano).pdf" ou "Sobrenome - Titulo"
    nome = Path(nome_arquivo).stem
    # Remover ano
    nome_limpo = re.sub(r'\s*[\(\[]\d{4}[\)\]]', '', nome)
    partes = re.split(r'\s*[-–—]\s*', nome_limpo, maxsplit=1)
    if len(partes) == 2 and len(partes[0].strip()) >= 3:
        candidato = partes[0].strip()
        # Aceitar nome com 1+ palavras (sobrenomes como "Bitencourt", "Gonçalves")
        if candidato[0].isupper():
            return candidato

    # 3. Buscar no texto (primeiras paginas)
    patterns = [
        r'(?:Autor|Author|Por|By)[:\s]+([A-ZÀ-Ú][a-zà-ú]+ [A-ZÀ-Ú][^\n]{3,50})',
        r'^([A-ZÀ-Ú][a-zà-ú]+ (?:de |do |da |dos |das )?[A-ZÀ-Ú][a-zà-ú]+(?:\s[A-ZÀ-Ú][a-zà-ú]+)?)\s*\n',
    ]
    for pattern in patterns:
        match = re.search(pattern, texto_amostra[:2000], re.MULTILINE)
        if match:
            return match.group(1).strip()[:60]

    return ""


def extrair_titulo(nome_arquivo, meta_pdf):
    """Extrai titulo: 1) metadados PDF, 2) nome do arquivo."""
    titulo = meta_pdf.get("titulo_pdf", "")
    if titulo and len(titulo) > 3:
        return titulo.strip()

    nome = Path(nome_arquivo).stem
    # Remover ano entre parenteses
    nome = re.sub(r'\s*[\(\[]\d{4}[\)\]]', '', nome)
    # Se tem "Autor - Titulo", pegar o titulo
    partes = re.split(r'\s*[-–—]\s*', nome, maxsplit=1)
    if len(partes) == 2:
        return partes[1].strip()

    return nome.strip()


def extrair_ano(nome_arquivo, meta_pdf, texto_amostra):
    """Extrai ano de publicacao."""
    # 1. Nome do arquivo
    match = re.search(r'[\(\[]?((?:19|20)\d{2})[\)\]]?', nome_arquivo)
    if match:
        return int(match.group(1))

    # 2. Texto (primeiras paginas)
    patterns = [
        r'(?:edi[cç][aã]o|ed\.)\s*(?:de\s+)?((?:19|20)\d{2})',
        r'(?:copyright|©)\s*((?:19|20)\d{2})',
        r'((?:19|20)\d{2})\s*(?:by|por|Editora)',
    ]
    for pattern in patterns:
        match = re.search(pattern, texto_amostra[:3000], re.IGNORECASE)
        if match:
            return int(match.group(1))

    return 0


def extrair_edicao(nome_arquivo, texto_amostra):
    """Extrai numero da edicao."""
    texto = nome_arquivo + " " + texto_amostra[:2000]
    patterns = [
        r'(\d+)[aªº°]?\s*(?:edi[cç][aã]o|ed\.)',
        r'(?:edi[cç][aã]o|ed\.)\s*(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, texto, re.IGNORECASE)
        if match:
            return f"{match.group(1)}a edicao"
    return ""


def detectar_materia(nome_arquivo, texto_amostra, caminho):
    """Detecta materia juridica automaticamente."""
    base = (nome_arquivo + " " + caminho + " " + texto_amostra[:5000]).lower()

    materias = {
        "Direito Civil": [
            "direito civil", "obrigações", "obrigacoes", "contratos",
            "responsabilidade civil", "família", "familia", "sucessões",
            "sucessoes", "direitos reais", "pessoa natural", "negócio jurídico",
            "negocio juridico", "posse", "propriedade",
        ],
        "Direito Penal": [
            "direito penal", "crime", "criminologia", "delito",
            "tipicidade", "antijuridicidade", "culpabilidade",
            "pena", "processo penal",
        ],
        "Processo Civil": [
            "processo civil", "processual civil", "cpc",
            "código de processo civil", "tutela provisória",
            "recursos cíveis", "execução civil",
        ],
        "Processo Penal": [
            "processo penal", "processual penal", "cpp",
            "inquérito policial", "ação penal",
        ],
        "Direito Constitucional": [
            "constitucional", "constituição", "constituicao",
            "direitos fundamentais", "controle de constitucionalidade",
            "poder constituinte", "direitos humanos",
        ],
        "Direito Administrativo": [
            "administrativo", "licitação", "licitacao",
            "servidor público", "ato administrativo",
            "poder de polícia", "concessão",
        ],
        "Direito Tributario": [
            "tributário", "tributario", "imposto", "tributo",
            "icms", "contribuição", "taxa", "fato gerador",
        ],
        "Direito do Trabalho": [
            "direito do trabalho", "trabalhista", "clt",
            "empregado", "empregador", "rescisão", "férias",
        ],
        "Direito Empresarial": [
            "empresarial", "comercial", "sociedade",
            "falência", "falencia", "recuperação judicial",
            "títulos de crédito",
        ],
        "Direito Ambiental": [
            "ambiental", "meio ambiente", "licenciamento ambiental",
        ],
        "Direito do Consumidor": [
            "consumidor", "cdc", "relação de consumo",
            "código de defesa do consumidor",
        ],
    }

    for materia, palavras in materias.items():
        if any(p in base for p in palavras):
            return materia

    return "Geral"


# ============================================================
# DETECCAO DE POSICAO DOUTRINARIA
# ============================================================

SINAIS_POSICAO = {
    "majoritaria": [
        "maioria da doutrina", "entendimento dominante", "posição consolidada",
        "doutrina majoritária", "corrente majoritária", "pacífico na doutrina",
        "entendimento pacífico", "posição predominante", "a doutrina é unânime",
    ],
    "minoritaria": [
        "parte da doutrina", "corrente minoritária", "há quem sustente",
        "posição minoritária", "alguns autores", "entendimento isolado",
    ],
    "critica": [
        "não concordamos", "equivoca-se", "merece crítica",
        "data venia", "com a devida vênia", "discordamos",
        "não nos parece correto", "criticável",
    ],
    "historica": [
        "historicamente", "direito romano", "tradicionalmente",
        "evolução histórica", "origem histórica", "no passado",
    ],
}


def detectar_posicao_doutrinaria(texto):
    """Detecta posicao doutrinaria do trecho: majoritaria, minoritaria, critica, historica, conceito, indefinida."""
    texto_lower = texto.lower()
    scores = {}
    for posicao, sinais in SINAIS_POSICAO.items():
        count = sum(1 for s in sinais if s in texto_lower)
        if count > 0:
            scores[posicao] = count

    if not scores:
        conceito_sinais = ["conceito", "define-se", "entende-se por", "consiste em",
                          "trata-se de", "pode ser definido"]
        if any(s in texto_lower for s in conceito_sinais):
            return "conceito"
        return "indefinida"

    return max(scores, key=scores.get)


# ============================================================
# CHUNKING INTELIGENTE
# ============================================================

def criar_chunks_pagina(texto_pagina, metadados, pagina_num, capitulo):
    """Divide o texto de uma pagina em chunks menores com metadados."""
    chunks = []

    # Se a pagina e pequena, usa como chunk unico
    if len(texto_pagina) <= CHUNK_SIZE + 100:
        if len(texto_pagina.strip()) >= 50:
            ch_id = _doctrine_hash(f"{metadados.get('work_id','')}|{capitulo or ''}")
            d_id = _doctrine_hash(f"{metadados.get('author_id','')}|{metadados.get('materia','')}|ch_{ch_id}")
            posicao = detectar_posicao_doutrinaria(texto_pagina)
            fonte = classificar_fonte(texto_pagina)
            meta = {
                **metadados,
                "page": pagina_num, "pagina": pagina_num, "capitulo": capitulo,
                "chapter_id": f"ch_{ch_id}", "doctrine_id": f"d_{d_id}",
                "posicao_doutrinaria": posicao,
                "fonte_normativa": fonte["fonte_normativa"],
                "orgao_julgador": fonte["orgao_julgador"],
                "artigo_referenciado": fonte["artigo_referenciado"],
                "peso_normativo": fonte["peso_normativo"],
            }
            chunks.append(Document(text=texto_pagina.strip(), metadata=meta))
        return chunks

    # Dividir em chunks menores
    avanco = CHUNK_SIZE - CHUNK_OVERLAP  # avancar 824 chars por chunk
    inicio = 0
    while inicio < len(texto_pagina):
        fim = min(inicio + CHUNK_SIZE, len(texto_pagina))

        # Tentar cortar em ponto natural (final de frase)
        if fim < len(texto_pagina):
            melhor_corte = -1
            for sep in [". ", ".\n", "\n\n", "\n", "; "]:
                pos = texto_pagina.rfind(sep, inicio + avanco // 2, fim + 50)
                if pos > melhor_corte:
                    melhor_corte = pos + len(sep)

            if melhor_corte > inicio + avanco // 2:
                fim = melhor_corte

        trecho = texto_pagina[inicio:fim].strip()
        if len(trecho) >= 50:
            ch_id = _doctrine_hash(f"{metadados.get('work_id','')}|{capitulo or ''}")
            d_id = _doctrine_hash(f"{metadados.get('author_id','')}|{metadados.get('materia','')}|ch_{ch_id}")
            posicao = detectar_posicao_doutrinaria(trecho)
            fonte = classificar_fonte(trecho)
            meta = {
                **metadados,
                "page": pagina_num,
                "pagina": pagina_num,
                "capitulo": capitulo,
                "chapter_id": f"ch_{ch_id}",
                "doctrine_id": f"d_{d_id}",
                "posicao_doutrinaria": posicao,
                "fonte_normativa": fonte["fonte_normativa"],
                "orgao_julgador": fonte["orgao_julgador"],
            }
            chunks.append(Document(text=trecho, metadata=meta))

        # Avancar posicao fixa (nunca menos que avanco)
        inicio += avanco

    return chunks


# ============================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================

start_time = time.time()
total_chunks_criados = 0
livros_processados = 0
livros_pulados = 0
livros_erro = 0
documentos_pendentes = []

logger.info(f"Buscando livros em: {PASTA_LIVROS}")

# Contar arquivos
todos_arquivos = []
for raiz, _, arquivos in os.walk(PASTA_LIVROS):
    for arquivo in sorted(arquivos):
        ext = arquivo.lower()
        if ext.endswith(".pdf") or ext.endswith(".epub"):
            todos_arquivos.append(os.path.join(raiz, arquivo))

logger.info(f"Encontrados: {len(todos_arquivos)} livros")
tamanho_total = sum(os.path.getsize(f) for f in todos_arquivos) / (1024**3)
logger.info(f"Tamanho total: {tamanho_total:.1f}GB")
logger.info("=" * 60)


def salvar_lote(docs):
    """Salva um lote de documentos no indice."""
    global documentos_pendentes
    if not docs:
        return

    if os.path.exists(os.path.join(PASTA_INDICE, "docstore.json")):
        storage = StorageContext.from_defaults(persist_dir=PASTA_INDICE)
        index = load_index_from_storage(storage)
        for d in docs:
            index.insert(d)
    else:
        index = VectorStoreIndex.from_documents(docs)

    index.storage_context.persist(persist_dir=PASTA_INDICE)
    documentos_pendentes = []


# Processar cada livro
for idx, caminho_completo in enumerate(todos_arquivos):
    arquivo = os.path.basename(caminho_completo)
    raiz = os.path.dirname(caminho_completo)
    ext = arquivo.lower()

    # Hash para deduplicacao
    file_hash = hash_arquivo(caminho_completo)

    if file_hash in controle:
        livros_pulados += 1
        continue

    logger.info(f"[{idx+1}/{len(todos_arquivos)}] {arquivo}")

    try:
        # Extrair texto
        if ext.endswith(".pdf"):
            paginas, meta_raw = ler_pdf(caminho_completo)
        elif ext.endswith(".epub"):
            paginas, meta_raw = ler_epub(caminho_completo)
        else:
            continue

        if not paginas or len(paginas) < 1:
            logger.warning("  Sem conteudo - ignorado")
            livros_erro += 1
            continue

        texto_amostra = meta_raw.get("texto_amostra", "")

        # Extrair ISBN e buscar metadados online
        texto_final = "\n".join(p["texto"] for p in paginas[-5:]) if len(paginas) > 5 else ""
        isbn = extrair_isbn(texto_amostra, texto_final)
        isbn_meta = None
        if isbn:
            logger.info(f"  ISBN encontrado: {isbn}")
            isbn_meta = buscar_isbn_online(isbn)

        # Extrair metadados (ISBN online tem prioridade)
        if isbn_meta and isbn_meta.get("autor"):
            autor = isbn_meta["autor"]
            titulo = isbn_meta.get("titulo") or extrair_titulo(arquivo, meta_raw)
            ano = isbn_meta.get("ano") or extrair_ano(arquivo, meta_raw, texto_amostra)
            editora = isbn_meta.get("editora", "")
            logger.info(f"  Metadados via ISBN ({isbn_meta.get('fonte','API')})")
        else:
            autor = extrair_autor(arquivo, meta_raw, texto_amostra)
            titulo = extrair_titulo(arquivo, meta_raw)
            ano = extrair_ano(arquivo, meta_raw, texto_amostra)
            editora = ""

        edicao = extrair_edicao(arquivo, texto_amostra)
        materia = detectar_materia(arquivo, texto_amostra, raiz)

        logger.info(f"  Titulo: {titulo}")
        logger.info(f"  Autor: {autor or '(nao detectado)'}")
        logger.info(f"  Ano: {ano or '?'} | Materia: {materia} | Paginas: {meta_raw.get('total_paginas', '?')}")
        if isbn:
            logger.info(f"  ISBN: {isbn}")

        # Metadados base para todos os chunks deste livro
        # Hierarchical doctrine IDs for Doctrine Graph Layer
        author_id = _doctrine_hash(f"{(autor or '').lower().strip()}")
        work_id = _doctrine_hash(f"{(autor or '').lower()}|{(titulo or '').lower()}|{edicao or ''}")

        metadados_base = {
            "arquivo": arquivo,
            "caminho": raiz,
            "ano": ano,
            "author": autor,
            "autor": autor,
            "title": titulo,
            "edicao": edicao,
            "editora": editora,
            "isbn": isbn,
            "materia": materia,
            "legal_subject": materia,
            "hash": file_hash,
            "author_id": f"a_{author_id}",
            "work_id": f"w_{work_id}",
        }

        # Criar chunks pagina por pagina
        chunks_livro = 0
        for pg in paginas:
            chunks = criar_chunks_pagina(
                pg["texto"],
                metadados_base,
                pg["pagina"],
                pg.get("capitulo", ""),
            )
            documentos_pendentes.extend(chunks)
            chunks_livro += len(chunks)

        total_chunks_criados += chunks_livro
        livros_processados += 1

        logger.info(f"  Chunks: {chunks_livro} | Total acumulado: {total_chunks_criados}")

        # Salvar no controle
        controle[file_hash] = {
            "arquivo": arquivo,
            "autor": autor,
            "titulo": titulo,
            "ano": ano,
            "edicao": edicao,
            "editora": editora,
            "isbn": isbn,
            "materia": materia,
            "paginas": meta_raw.get("total_paginas", 0),
            "chunks": chunks_livro,
            "indexado_em": datetime.now().isoformat(),
        }
        salvar_controle()

        # Salvar lote quando acumular bastante
        if len(documentos_pendentes) >= LOTE_SALVAR:
            logger.info(f"  Salvando lote de {len(documentos_pendentes)} chunks...")
            salvar_lote(documentos_pendentes)
            logger.info(f"  Lote salvo!")

    except Exception as e:
        livros_erro += 1
        logger.error(f"  ERRO: {e}")
        continue

# ============================================================
# SALVAR LOTE FINAL
# ============================================================

if documentos_pendentes:
    logger.info(f"Salvando lote final de {len(documentos_pendentes)} chunks...")
    salvar_lote(documentos_pendentes)
    logger.info("Salvo!")

# ============================================================
# RELATORIO FINAL
# ============================================================

elapsed = time.time() - start_time
horas = int(elapsed // 3600)
minutos = int((elapsed % 3600) // 60)
segundos = int(elapsed % 60)

logger.info("")
logger.info("=" * 60)
logger.info("INDEXACAO CONCLUIDA")
logger.info("=" * 60)
logger.info(f"Livros processados: {livros_processados}")
logger.info(f"Livros pulados (ja indexados): {livros_pulados}")
logger.info(f"Livros com erro: {livros_erro}")
logger.info(f"Total de chunks criados: {total_chunks_criados:,}")
logger.info(f"Tempo: {horas}h {minutos}min {segundos}s")
logger.info("")
logger.info("Arquivos gerados:")
logger.info(f"  {PASTA_INDICE}/           - indice vetorial")
logger.info(f"  {ARQUIVO_CONTROLE}   - controle de duplicatas")
logger.info(f"  indexacao.log         - log completo")
logger.info("")
logger.info("PROXIMO PASSO:")
logger.info(f"  1. Compacte '{PASTA_INDICE}/' e '{ARQUIVO_CONTROLE}' em um ZIP")
logger.info(f"  2. Importe pelo botao 'Importar ZIP' no JuristaAI")

if livros_erro > 0:
    logger.info("")
    logger.info(f"{livros_erro} livros com erro. Veja indexacao.log para detalhes.")
