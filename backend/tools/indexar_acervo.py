#!/usr/bin/env python3
"""
JuristaAI - Script de Indexacao Local
=====================================
Processa livros juridicos (PDF/EPUB) e cria banco vetorial para o JuristaAI.

Uso:
    python indexar_acervo.py --pasta "CAMINHO_DA_PASTA"

Autor: JuristaAI
"""

import os
import sys
import json
import hashlib
import argparse
import re
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    from sentence_transformers import SentenceTransformer
    import chromadb
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from tqdm import tqdm
except ImportError as e:
    print(f"\n❌ Dependência faltando: {e}")
    print("Execute: pip install -r requirements_local.txt")
    sys.exit(1)

# ============================================================
# CONFIGURAÇÃO
# ============================================================

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "jurista_legal_docs"

LEGAL_SEPARATORS = [
    "\n\nCAPÍTULO",
    "\n\nSEÇÃO",
    "\n\nArt.",
    "\n\nArtigo",
    "\n\n§",
    "\n\n",
    "\n",
    ". ",
    " ",
]

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("JuristaAI")

# ============================================================
# FUNÇÕES DE EXTRAÇÃO
# ============================================================

def compute_file_hash(file_path: str) -> str:
    """Calcula hash SHA256 do arquivo."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(8192), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def extract_pdf(file_path: str) -> Tuple[str, Dict, List[Dict]]:
    """Extrai texto e metadados de PDF."""
    doc = fitz.open(file_path)
    metadata = doc.metadata or {}
    total_pages = len(doc)
    
    full_text = ""
    page_texts = []
    
    for page_num in range(total_pages):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip():
            page_texts.append({"page": page_num + 1, "text": text.strip()})
            full_text += text + "\n\n"
    
    doc.close()
    
    meta = {
        "title": metadata.get("title", "") or "",
        "author": metadata.get("author", "") or "",
        "total_pages": total_pages,
    }
    
    year = _extract_year(metadata, full_text[:5000])
    if year:
        meta["year"] = year
    
    edition = _extract_edition(full_text[:5000])
    if edition:
        meta["edition"] = edition
    
    return full_text, meta, page_texts


def extract_epub(file_path: str) -> Tuple[str, Dict, List[Dict]]:
    """Extrai texto e metadados de EPUB."""
    book = epub.read_epub(file_path, options={'ignore_ncx': True})
    
    title = ""
    author = ""
    year = None
    
    title_meta = book.get_metadata('DC', 'title')
    if title_meta:
        title = title_meta[0][0] if title_meta[0] else ""
    
    author_meta = book.get_metadata('DC', 'creator')
    if author_meta:
        author = author_meta[0][0] if author_meta[0] else ""
    
    date_meta = book.get_metadata('DC', 'date')
    if date_meta:
        date_str = date_meta[0][0] if date_meta[0] else ""
        year_match = re.search(r'(\d{4})', date_str)
        if year_match:
            year = int(year_match.group(1))
    
    full_text = ""
    chapter_texts = []
    chapter_num = 0
    
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        content = item.get_content()
        soup = BeautifulSoup(content, 'lxml')
        text = soup.get_text(separator='\n', strip=True)
        if text.strip() and len(text.strip()) > 50:
            chapter_num += 1
            chapter_texts.append({"page": chapter_num, "text": text.strip()})
            full_text += text + "\n\n"
    
    meta = {
        "title": title,
        "author": author,
        "total_pages": chapter_num,
    }
    
    if year:
        meta["year"] = year
    elif not year:
        year = _extract_year({}, full_text[:5000])
        if year:
            meta["year"] = year
    
    edition = _extract_edition(full_text[:5000])
    if edition:
        meta["edition"] = edition
    
    return full_text, meta, chapter_texts


def _extract_year(metadata: Dict, text_sample: str) -> Optional[int]:
    """Tenta extrair ano de publicação."""
    for key in ['creationDate', 'modDate', 'date']:
        if key in metadata and metadata[key]:
            match = re.search(r'(19[5-9]\d|20[0-2]\d)', str(metadata[key]))
            if match:
                return int(match.group(1))
    
    patterns = [
        r'(?:edição|edicao|ed\.)\s*(?:de\s+)?(19[5-9]\d|20[0-2]\d)',
        r'(?:copyright|©)\s*(19[5-9]\d|20[0-2]\d)',
        r'(?:publicado|publicação)\s*(?:em\s+)?(19[5-9]\d|20[0-2]\d)',
        r'(19[5-9]\d|20[0-2]\d)\s*(?:by|por)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text_sample, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_edition(text_sample: str) -> Optional[str]:
    """Tenta extrair edição."""
    patterns = [
        r'(\d+)[ªaº]?\s*(?:edição|edicao|ed\.)',
        r'(?:edição|edicao|ed\.)\s*(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text_sample, re.IGNORECASE)
        if match:
            return f"{match.group(1)}ª edição"
    return None


def guess_metadata_from_filename(filename: str) -> Dict:
    """Tenta extrair metadados do nome do arquivo."""
    name = Path(filename).stem
    result = {}
    
    year_match = re.search(r'[\(\[](\d{4})[\)\]]', name)
    if year_match:
        result['year'] = int(year_match.group(1))
        name = name[:year_match.start()] + name[year_match.end():]
    
    parts = re.split(r'\s*[-–—]\s*', name.strip(), maxsplit=1)
    if len(parts) == 2:
        result['author'] = parts[0].strip()
        result['title'] = parts[1].strip()
    else:
        result['title'] = name.strip()
    
    return result


# ============================================================
# CHUNKING
# ============================================================

def create_chunks(text: str, metadata: Dict, page_texts: List[Dict],
                  chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Dict]:
    """Divide texto em chunks com metadados."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=LEGAL_SEPARATORS,
        length_function=len,
    )
    
    chunks = []
    chunk_index = 0
    
    for page_info in page_texts:
        page_num = page_info.get("page", 0)
        text = page_info["text"]
        if not text.strip():
            continue
        
        page_chunks = splitter.split_text(text)
        for chunk_text in page_chunks:
            if not chunk_text.strip() or len(chunk_text.strip()) < 30:
                continue
            chunks.append({
                "text": chunk_text.strip(),
                "metadata": {
                    "doc_id": metadata.get("doc_id", ""),
                    "author": metadata.get("author", ""),
                    "title": metadata.get("title", ""),
                    "year": metadata.get("year", ""),
                    "edition": metadata.get("edition", ""),
                    "legal_subject": metadata.get("legal_subject", ""),
                    "legal_institute": metadata.get("legal_institute", ""),
                    "page": page_num,
                    "chunk_index": chunk_index,
                }
            })
            chunk_index += 1
    
    return chunks


# ============================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================

def find_books(pasta: str, apenas_pdf: bool = False, apenas_epub: bool = False) -> List[Path]:
    """Encontra todos os livros na pasta (recursivo)."""
    extensions = []
    if not apenas_epub:
        extensions.append(".pdf")
    if not apenas_pdf:
        extensions.append(".epub")
    
    books = []
    for ext in extensions:
        books.extend(Path(pasta).rglob(f"*{ext}"))
    
    # Ordenar por nome
    books.sort(key=lambda p: p.name.lower())
    return books


def load_progress(export_dir: Path) -> Dict:
    """Carrega progresso anterior para retomar."""
    progress_file = export_dir / "indexacao_log.json"
    if progress_file.exists():
        with open(progress_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed_hashes": [], "documents": [], "errors": [], "stats": {}}


def save_progress(export_dir: Path, progress: Dict):
    """Salva progresso."""
    progress_file = export_dir / "indexacao_log.json"
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(
        description="JuristaAI — Indexação Local de Acervo Jurídico",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python indexar_acervo.py --pasta "C:\\Livros\\Direito"
  python indexar_acervo.py --pasta "./meus_livros" --retomar
  python indexar_acervo.py --pasta "./meus_livros" --chunk-size 1200 --overlap 250
"""
    )
    parser.add_argument("--pasta", required=True, help="Pasta com os livros jurídicos")
    parser.add_argument("--output", default="./jurista_export", help="Pasta de saída (padrão: ./jurista_export)")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Tamanho do chunk (padrão: 1000)")
    parser.add_argument("--overlap", type=int, default=200, help="Overlap entre chunks (padrão: 200)")
    parser.add_argument("--apenas-pdf", action="store_true", help="Processar apenas PDFs")
    parser.add_argument("--apenas-epub", action="store_true", help="Processar apenas EPUBs")
    parser.add_argument("--retomar", action="store_true", help="Retomar indexação anterior")
    parser.add_argument("--batch-size", type=int, default=64, help="Tamanho do batch de embeddings (padrão: 64)")
    
    args = parser.parse_args()
    
    pasta = Path(args.pasta)
    if not pasta.exists():
        logger.error(f"❌ Pasta não encontrada: {pasta}")
        sys.exit(1)
    
    export_dir = Path(args.output)
    export_dir.mkdir(parents=True, exist_ok=True)
    vectordb_dir = export_dir / "vectordb"
    vectordb_dir.mkdir(parents=True, exist_ok=True)
    
    # ============================
    # 1. Encontrar livros
    # ============================
    logger.info(f"📂 Buscando livros em: {pasta}")
    books = find_books(str(pasta), args.apenas_pdf, args.apenas_epub)
    logger.info(f"📚 Encontrados: {len(books)} livros")
    
    if not books:
        logger.error("❌ Nenhum livro encontrado!")
        sys.exit(1)
    
    # Mostrar resumo por tipo
    pdfs = [b for b in books if b.suffix.lower() == '.pdf']
    epubs = [b for b in books if b.suffix.lower() == '.epub']
    total_size = sum(b.stat().st_size for b in books) / (1024**3)
    logger.info(f"   PDFs: {len(pdfs)} | EPUBs: {len(epubs)} | Tamanho total: {total_size:.1f}GB")
    
    # ============================
    # 2. Carregar progresso
    # ============================
    progress = load_progress(export_dir)
    processed_hashes = set(progress.get("processed_hashes", []))
    
    if args.retomar and processed_hashes:
        logger.info(f"🔄 Retomando: {len(processed_hashes)} livros já processados")
    
    # ============================
    # 3. Carregar modelo de embeddings
    # ============================
    logger.info(f"🧠 Carregando modelo de embeddings: {EMBEDDING_MODEL}")
    logger.info("   (primeira vez pode demorar para baixar ~500MB)")
    model = SentenceTransformer(EMBEDDING_MODEL)
    embed_dim = model.get_sentence_embedding_dimension()
    logger.info(f"   ✅ Modelo carregado. Dimensão: {embed_dim}")
    
    # ============================
    # 4. Inicializar ChromaDB
    # ============================
    logger.info(f"💾 Inicializando ChromaDB em: {vectordb_dir}")
    chroma_client = chromadb.PersistentClient(path=str(vectordb_dir))
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    logger.info(f"   Chunks existentes: {collection.count()}")
    
    # ============================
    # 5. Processar livros
    # ============================
    start_time = time.time()
    total_chunks_added = 0
    books_processed = 0
    books_skipped = 0
    books_errored = 0
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("INICIANDO INDEXAÇÃO")
    logger.info("=" * 60)
    
    for i, book_path in enumerate(tqdm(books, desc="Indexando", unit="livro")):
        file_name = book_path.name
        
        try:
            # Calcular hash
            file_hash = compute_file_hash(str(book_path))
            
            # Pular se já processado
            if file_hash in processed_hashes:
                books_skipped += 1
                continue
            
            logger.info(f"\n📖 [{i+1}/{len(books)}] {file_name}")
            
            # Extrair texto
            ext = book_path.suffix.lower()
            if ext == '.pdf':
                full_text, meta, page_texts = extract_pdf(str(book_path))
            elif ext == '.epub':
                full_text, meta, page_texts = extract_epub(str(book_path))
            else:
                continue
            
            if not full_text.strip() or len(full_text.strip()) < 100:
                logger.warning("   ⚠️ Texto insuficiente extraído. Pulando.")
                books_errored += 1
                progress["errors"].append({
                    "file": file_name,
                    "error": "Texto insuficiente",
                    "time": datetime.now().isoformat()
                })
                continue
            
            # Complementar metadados com nome do arquivo
            filename_meta = guess_metadata_from_filename(file_name)
            if not meta.get("title"):
                meta["title"] = filename_meta.get("title", book_path.stem)
            if not meta.get("author"):
                meta["author"] = filename_meta.get("author", "")
            if not meta.get("year") and filename_meta.get("year"):
                meta["year"] = filename_meta["year"]
            
            # Gerar ID do documento
            import uuid
            doc_id = str(uuid.uuid4())
            meta["doc_id"] = doc_id
            
            logger.info(f"   Título: {meta.get('title', '?')}")
            logger.info(f"   Autor: {meta.get('author', '?')}")
            logger.info(f"   Ano: {meta.get('year', '?')}")
            logger.info(f"   Páginas: {meta.get('total_pages', '?')}")
            logger.info(f"   Texto: {len(full_text):,} caracteres")
            
            # Criar chunks
            chunks = create_chunks(
                full_text, meta, page_texts,
                chunk_size=args.chunk_size,
                chunk_overlap=args.overlap
            )
            
            if not chunks:
                logger.warning("   ⚠️ Nenhum chunk criado. Pulando.")
                books_errored += 1
                continue
            
            logger.info(f"   Chunks: {len(chunks)}")
            
            # Gerar embeddings e indexar em batches
            batch_size = args.batch_size
            for batch_start in range(0, len(chunks), batch_size):
                batch_end = min(batch_start + batch_size, len(chunks))
                batch = chunks[batch_start:batch_end]
                
                texts = [c["text"] for c in batch]
                metadatas = []
                ids = []
                
                for c in batch:
                    m = c["metadata"].copy()
                    # ChromaDB requer valores string/int/float/bool
                    for key, value in m.items():
                        if value is None:
                            m[key] = ""
                    metadatas.append(m)
                    ids.append(f"{doc_id}_chunk_{m['chunk_index']}")
                
                # Gerar embeddings
                embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
                
                # Inserir no ChromaDB
                collection.upsert(
                    ids=ids,
                    documents=texts,
                    embeddings=embeddings.tolist(),
                    metadatas=metadatas
                )
            
            total_chunks_added += len(chunks)
            books_processed += 1
            processed_hashes.add(file_hash)
            
            # Salvar metadados do documento
            doc_info = {
                "id": doc_id,
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "year": meta.get("year"),
                "edition": meta.get("edition", ""),
                "total_pages": meta.get("total_pages"),
                "total_chunks": len(chunks),
                "file_name": file_name,
                "file_hash": file_hash,
                "file_type": ext.replace(".", ""),
                "file_size": book_path.stat().st_size,
                "status": "indexed",
                "indexed_at": datetime.now().isoformat()
            }
            progress["documents"].append(doc_info)
            
            # Salvar progresso periodicamente
            progress["processed_hashes"] = list(processed_hashes)
            if books_processed % 5 == 0:  # A cada 5 livros
                save_progress(export_dir, progress)
                logger.info(f"   💾 Progresso salvo ({books_processed} livros, {total_chunks_added:,} chunks)")
            
            logger.info(f"   ✅ Indexado! ({len(chunks)} chunks)")
            
        except Exception as e:
            books_errored += 1
            logger.error(f"   ❌ Erro: {e}")
            progress["errors"].append({
                "file": file_name,
                "error": str(e),
                "time": datetime.now().isoformat()
            })
            continue
    
    # ============================
    # 6. Salvar resultado final
    # ============================
    elapsed = time.time() - start_time
    elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
    
    progress["processed_hashes"] = list(processed_hashes)
    progress["stats"] = {
        "total_books_found": len(books),
        "books_processed": books_processed,
        "books_skipped": books_skipped,
        "books_errored": books_errored,
        "total_chunks": total_chunks_added,
        "total_chunks_in_db": collection.count(),
        "processing_time": elapsed_str,
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.overlap,
        "embedding_model": EMBEDDING_MODEL,
        "completed_at": datetime.now().isoformat()
    }
    save_progress(export_dir, progress)
    
    # Salvar metadados separado (para importar no MongoDB)
    metadata_file = export_dir / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(progress["documents"], f, ensure_ascii=False, indent=2, default=str)
    
    # ============================
    # 7. Relatório final
    # ============================
    logger.info("")
    logger.info("=" * 60)
    logger.info("INDEXAÇÃO CONCLUÍDA")
    logger.info("=" * 60)
    logger.info(f"📚 Livros processados: {books_processed}")
    logger.info(f"⏭️  Livros pulados (já indexados): {books_skipped}")
    logger.info(f"❌ Livros com erro: {books_errored}")
    logger.info(f"📝 Total de chunks: {total_chunks_added:,}")
    logger.info(f"💾 Chunks no banco: {collection.count():,}")
    logger.info(f"⏱️  Tempo: {elapsed_str}")
    logger.info("")
    logger.info(f"📦 Exportado para: {export_dir}")
    logger.info("   vectordb/     — banco de vetores ChromaDB")
    logger.info("   metadata.json — metadados dos livros")
    logger.info("   indexacao_log.json — log completo")
    
    # Tamanho da exportação
    export_size = sum(
        f.stat().st_size for f in export_dir.rglob('*') if f.is_file()
    ) / (1024**3)
    logger.info("")
    logger.info(f"📊 Tamanho da exportação: {export_size:.2f}GB")
    logger.info("")
    logger.info(f"Próximo passo: transfira a pasta '{export_dir}' para o servidor JuristaAI")
    
    if books_errored > 0:
        logger.info("")
        logger.info(f"⚠️  {books_errored} livros tiveram erro. Veja indexacao_log.json para detalhes.")


if __name__ == "__main__":
    main()
