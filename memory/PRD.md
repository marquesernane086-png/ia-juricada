# JuristaAI - PRD (Product Requirements Document)

## Visão Geral
JuristaAI é uma IA jurídica doutrinária avançada que funciona como um jurista acadêmico digital, capaz de consultar livros jurídicos (PDF/EPUB), comparar posições doutrinárias, e produzir fundamentação jurídica estruturada.

## Arquitetura
- **Backend**: FastAPI (Python) com módulos independentes
- **Frontend**: React + Tailwind + shadcn/ui
- **Database**: MongoDB (metadados) + ChromaDB (vetores)
- **Embeddings**: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (local)
- **LLM**: OpenAI GPT-4o-mini via Emergent proxy

## Módulos Implementados

### 1. Ingestion Service (services/ingestion_service.py)
- Leitura de PDF (PyMuPDF) e EPUB (ebooklib)
- Extração de texto e metadados
- Hash SHA256 para controle de duplicidade
- Extração automática de ano, edição, autor

### 2. Indexing Service (services/indexing_service.py)
- Chunking com separadores jurídicos (CAPÍTULO, SEÇÃO, Art.)
- Metadados por chunk (autor, título, ano, edição, matéria, instituto)
- Peso temporal: `peso = 1 + ((ano - 1950) / 100)`
- Rastreamento de página por chunk

### 3. Vector Service (services/vector_service.py)
- Embeddings locais via SentenceTransformers
- ChromaDB persistente com similaridade coseno
- Busca semântica com filtros de metadados
- Operações de CRUD em chunks

### 4. Reasoning Service (services/reasoning_service.py)
- Agrupamento por autor
- Peso temporal (doutrina recente priorizada)
- Detecção de divergência doutrinária
- Geração de resposta estruturada via OpenAI

### 5. Chat Service (services/chat_service.py)
- Orquestração do pipeline RAG completo
- Resposta com fontes e tempo de processamento

## Formato de Resposta
```
## RELATÓRIO
Fundamentação doutrinária com citações (AUTOR. Obra. Ano)

## POSIÇÕES DOUTRINÁRIAS
Comparação entre autores clássicos e modernos

## EVOLUÇÃO DO ENTENDIMENTO
Mudanças históricas no entendimento

## CONCLUSÃO
Síntese técnica fundamentada
```

## API Endpoints
- POST /api/documents/upload - Upload de livros jurídicos
- GET /api/documents - Listar documentos
- PATCH /api/documents/{id} - Editar metadados
- DELETE /api/documents/{id} - Remover documento
- POST /api/documents/{id}/reindex - Reindexar
- POST /api/chat - Consulta jurídica doutrinária
- GET /api/chat/stats - Estatísticas do sistema
- GET /api/health - Health check

## Status: MVP Completo ✅
