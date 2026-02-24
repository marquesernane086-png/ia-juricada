# 🏛️ JURISTAAI — DOCUMENTAÇÃO TÉCNICA COMPLETA
**Versão 1.0 | Fevereiro 2026**

---

## 1. VISÃO GERAL DO PROJETO

### 1.1 O que é
JuristaAI é uma Inteligência Artificial especializada em **Direito brasileiro** que funciona como **jurista acadêmico digital**. O sistema ingere livros jurídicos doutrinários (PDF/EPUB), indexa semanticamente, e responde perguntas jurídicas usando exclusivamente o conteúdo indexado, com citações verificadas.

### 1.2 O que NÃO é
- NÃO é um chatbot genérico
- NÃO usa conhecimento geral do modelo de linguagem
- NÃO inventa citações ou referências
- NÃO mistura doutrina com jurisprudência (futuramente separados)

### 1.3 Objetivo principal
Consultar livros jurídicos digitais e produzir **fundamentação doutrinária estruturada** com:
- Citações verificadas no formato acadêmico (AUTOR. Obra. Ano, p. X)
- Comparação entre posições doutrinárias de diferentes autores
- Detecção de evolução histórica do entendimento jurídico
- Preservação de posições minoritárias

---

## 2. NÚMEROS E ESTADO ATUAL

| Métrica | Valor |
|---------|-------|
| Arquivos de código | 78 |
| Linhas de código | ~8.500 |
| Chunks no vector store (importação anterior) | 37.891 |
| Livros sendo indexados (máquina do usuário) | 3.764 |
| Acervo total | ~36GB |
| Agentes ativos no pipeline | 5 |
| Agentes em modo preparação | 6 |
| Tempo médio de resposta | 20-35 segundos |
| Modelo de embedding | paraphrase-multilingual-MiniLM-L12-v2 (384 dims, local) |
| Modelo LLM | GPT-4o-mini via Emergent proxy |

---

## 3. STACK TÉCNICA DETALHADA

### 3.1 Backend
- **Framework**: FastAPI (Python 3.11)
- **Servidor**: Uvicorn com hot-reload via Supervisor
- **Porta interna**: 8001 (mapeado via Kubernetes ingress com prefixo /api)

### 3.2 Frontend
- **Framework**: React 19 (CRA + CRACO)
- **UI**: Tailwind CSS + shadcn/ui (48 componentes pré-instalados)
- **Markdown**: react-markdown + remark-gfm para renderizar respostas
- **HTTP**: axios com timeout de 120 segundos
- **Porta**: 3000

### 3.3 Banco de Dados
- **MongoDB** (motor async): metadados dos livros (título, autor, ano, status, hash)
- **Database**: `jurista_ai`
- **Coleção**: `documents`
- **Índices**: id (unique), file_hash, status, author, legal_subject

### 3.4 Vector Store
- **LlamaIndex VectorStoreIndex**: armazenamento persistente em disco
- **Diretório**: `/app/backend/data/indice/`
- **Formato**: docstore.json + index_store.json + vector_store.json
- **Embedding**: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
  - Dimensão: 384
  - Multilingual (suporta português)
  - Execução local (sem API externa para embedding)

### 3.5 LLM
- **Modelo**: OpenAI GPT-4o-mini
- **Proxy**: Emergent Integration Proxy (`https://integrations.emergentagent.com/llm`)
- **API Key**: sk-emergent-* (chave Emergent)
- **Temperatura**: 0.3 (baixa para precisão jurídica)
- **Max tokens**: 4.000 por resposta
- **Uso**: 2 chamadas por pergunta (1 para Legal Issue Extractor + 1 para Reasoning)

### 3.6 Servidor Cloud
- **Plataforma**: Kubernetes (Emergent)
- **RAM**: 15GB (8GB disponíveis)
- **CPU**: 4 cores
- **Disco**: 95GB (79GB livres)
- **URL**: https://juristico-ia.preview.emergentagent.com

---

## 4. ARQUITETURA DE ARQUIVOS

```
/app/
├── backend/
│   ├── server.py                              # FastAPI app principal
│   ├── .env                                   # Variáveis de ambiente
│   ├── requirements.txt                       # Dependências Python
│   │
│   ├── models/
│   │   └── schemas.py                         # Pydantic schemas (7 modelos)
│   │       ├── DocumentMetadata               # Metadados de livro
│   │       ├── DocumentUploadResponse         # Resposta de upload
│   │       ├── DocumentListResponse           # Lista de documentos
│   │       ├── DocumentUpdateRequest          # Atualização de metadados
│   │       ├── ChatRequest                    # Pergunta do usuário
│   │       ├── ChatResponse                   # Resposta completa
│   │       ├── SourceReference                # Referência de fonte
│   │       └── SystemStats                    # Estatísticas do sistema
│   │
│   ├── services/                              # 🔵 AGENTES ATIVOS
│   │   ├── legal_issue_extractor.py           # [0] Decomposição da pergunta
│   │   ├── vector_service.py                  # [1] Busca vetorial LlamaIndex
│   │   ├── doctrine_comparator.py             # [2] Comparação doutrinária
│   │   ├── reasoning_service.py               # [3] Raciocínio jurídico (LLM)
│   │   ├── citation_guardian.py               # [4] Validação de citações
│   │   ├── chat_service.py                    # Orquestrador do pipeline
│   │   ├── ingestion_service.py               # Leitura PDF/EPUB
│   │   └── indexing_service.py                # Chunking + peso temporal
│   │
│   ├── services/agents/                       # 🔴 AGENTES EM PREPARAÇÃO
│   │   ├── __init__.py                        # Registry (todos DISABLED)
│   │   ├── procedural_strategy.py             # Recursos cabíveis
│   │   ├── decision_analyzer.py               # Análise de sentença
│   │   ├── legal_draft_generator.py           # Blueprint de peças
│   │   ├── deadline_agent.py                  # Contagem de prazos
│   │   ├── jurisprudence_retrieval.py         # Busca jurisprudência
│   │   └── legal_task_router.py               # Roteador central
│   │
│   ├── routes/                                # API endpoints
│   │   ├── chat_routes.py                     # POST /api/chat, GET /api/chat/stats
│   │   ├── document_routes.py                 # CRUD documentos
│   │   └── import_routes.py                   # Importar ZIP (background)
│   │
│   ├── data/
│   │   ├── indice/                            # LlamaIndex vector store persistente
│   │   │   ├── docstore.json                  # Documentos/chunks armazenados
│   │   │   ├── index_store.json               # Índice de busca
│   │   │   └── default__vector_store.json     # Vetores de embedding
│   │   └── uploads/                           # PDFs + ZIPs enviados
│   │
│   └── tools/                                 # Script de indexação local
│       ├── indexar_acervo.py                  # Script definitivo (733 linhas)
│       ├── requirements_local.txt             # Dependências locais
│       └── README_INDEXACAO.md                # Instruções
│
├── frontend/
│   └── src/
│       ├── App.js                             # Layout: sidebar + navegação
│       ├── App.css                            # Estilos customizados
│       ├── index.css                          # Tema jurídico (tons âmbar)
│       └── components/
│           ├── ChatPage.jsx                   # Interface de chat
│           ├── DocumentsPage.jsx              # Gerenciamento de acervo
│           └── ui/                            # 48 componentes shadcn/ui
│
└── memory/
    └── PRD.md                                 # Product Requirements Document
```

---

## 5. PIPELINE RAG COMPLETO (5 agentes ativos)

### Fluxo detalhado de uma pergunta:

```
USUÁRIO: "O que é vício redibitório?"
                    │
                    ▼
╔══════════════════════════════════════════════════════════╗
║  [0] LEGAL ISSUE EXTRACTOR                               ║
║  Arquivo: services/legal_issue_extractor.py              ║
║                                                          ║
║  Entrada: pergunta bruta do usuário                      ║
║  Processo:                                               ║
║    - Chama GPT-4o-mini com prompt classificador          ║
║    - Temperatura: 0.1 (máxima precisão)                  ║
║    - Max tokens: 500                                     ║
║  Saída JSON:                                             ║
║    {                                                     ║
║      "legal_area": "Direito Civil",                      ║
║      "legal_institute": "vício redibitório",             ║
║      "core_questions": [                                 ║
║        "O que caracteriza o vício redibitório?",         ║
║        "Quais os efeitos do vício redibitório?"          ║
║      ],                                                  ║
║      "related_concepts": [                               ║
║        "defeito oculto", "ação redibitória",             ║
║        "quanti minoris", "garantia legal"                ║
║      ],                                                  ║
║      "keywords_for_retrieval": [                         ║
║        "vício redibitório", "defeito oculto",            ║
║        "art 441 código civil", "ação estimatória"        ║
║      ],                                                  ║
║      "controversy_points": [                             ║
║        "cláusula no estado em que se encontra"           ║
║      ]                                                   ║
║    }                                                     ║
║                                                          ║
║  Também gera: enhanced_query (pergunta + keywords)       ║
║  Tempo: ~2-3 segundos                                    ║
╚══════════════════════════════════════════════════════════╝
                    │
                    ▼
╔══════════════════════════════════════════════════════════╗
║  [1] VECTOR RETRIEVAL                                    ║
║  Arquivo: services/vector_service.py                     ║
║                                                          ║
║  Entrada: enhanced_query (pergunta + keywords)           ║
║  Processo:                                               ║
║    1. Gera embedding da query (MiniLM, 384 dims)         ║
║    2. Busca os 15 chunks mais similares no LlamaIndex    ║
║    3. Para cada chunk retornado:                         ║
║       - Extrai metadados (autor, título, ano, página)    ║
║       - Parseia formato "Autor, Ano. Título" se needed   ║
║       - Calcula score de similaridade                    ║
║    4. Filtra: score mínimo 0.20                          ║
║                                                          ║
║  Saída: Lista de chunks com texto + metadados + score    ║
║  Tempo: ~1-2 segundos                                    ║
╚══════════════════════════════════════════════════════════╝
                    │
                    ▼
╔══════════════════════════════════════════════════════════╗
║  [2] DOCTRINE COMPARATOR                                 ║
║  Arquivo: services/doctrine_comparator.py                ║
║                                                          ║
║  Entrada: chunks filtrados do vector retrieval            ║
║  Processo:                                               ║
║    1. cluster_by_author_and_work()                       ║
║       - Agrupa: Autor → Obra → Edição → Chunks          ║
║    2. detect_edition_evolution()                         ║
║       - Mesmo autor, edições diferentes                  ║
║       - Detecta span temporal (ex: 2005 → 2020)         ║
║    3. compare_authors()                                  ║
║       - Compara autores diferentes sobre mesmo tema      ║
║       - Detecta gap temporal (>10 anos)                  ║
║       - Classifica: evolução vs conflito                 ║
║    4. detect_minority_positions()                        ║
║       - Autor com <30% dos chunks = minoritário          ║
║       - Marca para preservação obrigatória               ║
║    5. build_doctrine_context()                           ║
║       - Gera texto adicional para o LLM:                 ║
║         "POSIÇÕES MINORITÁRIAS DETECTADAS"               ║
║         "EVOLUÇÃO ENTRE EDIÇÕES"                         ║
║         "COMPARAÇÕES ENTRE AUTORES"                      ║
║                                                          ║
║  Saída: analysis dict + doctrine_context string          ║
║  Tempo: <100ms (processamento local)                     ║
╚══════════════════════════════════════════════════════════╝
                    │
                    ▼
╔══════════════════════════════════════════════════════════╗
║  [3] LEGAL REASONING AGENT                               ║
║  Arquivo: services/reasoning_service.py                  ║
║                                                          ║
║  Entrada: pergunta + chunks + doctrine_context           ║
║  Processo:                                               ║
║    1. apply_temporal_weighting()                         ║
║       - peso = 1 + ((ano - 1950) / 100)                  ║
║       - Livro de 2020: peso 1.70                         ║
║       - Livro de 1990: peso 1.40                         ║
║       - Score final = score_semantic × peso_temporal      ║
║    2. group_by_author()                                  ║
║       - Organiza fontes por autor                        ║
║    3. detect_divergence()                                ║
║       - Compara autores em pares                         ║
║       - Detecta gap temporal >10 anos                    ║
║    4. build_context()                                    ║
║       - Monta string formatada:                          ║
║         "FONTES DOUTRINÁRIAS RECUPERADAS DO ACERVO"      ║
║         Para cada autor:                                 ║
║           Obra, Ano, Página, Capítulo, Relevância        ║
║           Trecho do texto                                ║
║         + Indicadores de divergência                     ║
║         + Contexto do Doctrine Comparator                ║
║    5. Chama GPT-4o-mini com:                             ║
║       - System prompt: jurista civilista brasileiro       ║
║       - User message: pergunta + contexto + instruções   ║
║       - Temperatura: 0.3                                 ║
║       - Max tokens: 4.000                                ║
║                                                          ║
║  SYSTEM PROMPT inclui:                                   ║
║    - "Responda APENAS com base nos trechos"              ║
║    - "NÃO invente citações"                              ║
║    - "Distinguir CC vs CDC"                              ║
║    - "Distinguir subjetiva vs objetiva"                  ║
║    - "Respeitar hierarquia normativa"                    ║
║    - "Preservar posições minoritárias"                   ║
║    - Citação: (AUTOR. Obra. Ano, p. PÁGINA)              ║
║                                                          ║
║  Saída: resposta estruturada em markdown:                ║
║    ## RELATÓRIO                                          ║
║    ## POSIÇÕES DOUTRINÁRIAS                              ║
║    ## EVOLUÇÃO DO ENTENDIMENTO                           ║
║    ## CONCLUSÃO                                          ║
║                                                          ║
║  Tempo: ~15-30 segundos (depende do LLM)                 ║
╚══════════════════════════════════════════════════════════╝
                    │
                    ▼
╔══════════════════════════════════════════════════════════╗
║  [4] CITATION GUARDIAN                                   ║
║  Arquivo: services/citation_guardian.py                  ║
║                                                          ║
║  Entrada: resposta do LLM + chunks recuperados           ║
║  Processo:                                               ║
║    1. extract_citations()                                ║
║       - Regex multi-formato:                             ║
║         (AUTOR. Título. Ano, p. X)                       ║
║         (AUTOR. Título. Ano)                             ║
║         (AUTOR, Título, Ano, p. X)                       ║
║    2. Para CADA citação encontrada:                      ║
║       validate_citation()                                ║
║       - Normaliza texto (remove acentos, lowercase)      ║
║       - Calcula similaridade com SequenceMatcher         ║
║       - Score ponderado:                                 ║
║         Autor: 45%                                       ║
║         Título: 35%                                      ║
║         Ano: 20%                                         ║
║       - Threshold mínimo: 0.45                           ║
║    3. Citações inválidas:                                ║
║       - Marcadas com [⚠️ citação não verificada]         ║
║    4. Gera relatório de validação                        ║
║                                                          ║
║  Saída: resposta limpa + relatório de citações           ║
║  Tempo: <100ms (processamento local)                     ║
╚══════════════════════════════════════════════════════════╝
                    │
                    ▼
              RESPOSTA FINAL
         (JSON com answer + sources)
```

---

## 6. SCRIPT DE INDEXAÇÃO LOCAL (indexar_acervo.py)

### 6.1 Configuração
- **Caminho**: `C:\Users\joaop\OneDrive\Faculdade UNESA\LIVROS`
- **Chunk size**: 1.024 caracteres
- **Overlap**: 200 caracteres
- **Lote de salvamento**: a cada 200 chunks
- **Checkpoint**: `controle_index.json` (SHA256 por arquivo)

### 6.2 Fluxo por livro

```
Arquivo PDF/EPUB
       │
       ├─ 1. Hash SHA256 → verifica controle_index.json → pula se já existe
       │
       ├─ 2. Leitura:
       │     PDF: fitz.open() → página por página → detecta capítulo
       │     EPUB: ebooklib → capítulo por capítulo → detecta capítulo
       │
       ├─ 3. Extração ISBN (regex nas primeiras/últimas 5 páginas):
       │     Padrões: ISBN-13 (978/979...), ISBN-10
       │     Se encontrou → Google Books API → Open Library API
       │
       ├─ 4. Metadados (cascata de prioridade):
       │     Autor:  ISBN online → metadado PDF → nome arquivo → texto
       │     Título: ISBN online → metadado PDF → nome arquivo
       │     Ano:    nome arquivo → texto (edição/copyright)
       │     Edição: nome arquivo + texto
       │     Matéria: detecção automática (13 áreas do direito)
       │
       ├─ 5. Detecção de capítulo (regex):
       │     CAPÍTULO I, SEÇÃO II, TÍTULO III, PARTE IV, LIVRO V
       │
       ├─ 6. Chunking inteligente por página:
       │     - Se página ≤ 1124 chars → chunk único
       │     - Se maior → divide em ~1024 chars com overlap 200
       │     - Corta em final de frase (". " ou "\n")
       │     - Cada chunk guarda: autor, título, ano, ISBN, matéria,
       │       página, capítulo, edição, editora, hash
       │
       ├─ 7. Embedding: MiniLM multilingual (384 dims, local)
       │
       ├─ 8. Salva no LlamaIndex VectorStoreIndex
       │
       └─ 9. Atualiza controle_index.json com metadados completos
```

### 6.3 Matérias detectadas automaticamente (13)
1. Direito Civil
2. Direito Penal
3. Processo Civil
4. Processo Penal
5. Direito Constitucional
6. Direito Administrativo
7. Direito Tributário
8. Direito do Trabalho
9. Direito Empresarial
10. Direito Ambiental
11. Direito do Consumidor
12. Direito Internacional (futuro)
13. Geral (fallback)

### 6.4 Metadados salvos por livro no controle_index.json
```json
{
  "hash_sha256": {
    "arquivo": "Goncalves - Responsabilidade Civil (2012).pdf",
    "autor": "Carlos Roberto Gonçalves",
    "titulo": "Curso de Responsabilidade Civil",
    "ano": 2012,
    "edicao": "15a edicao",
    "editora": "Saraiva",
    "isbn": "9788502083790",
    "materia": "Direito Civil",
    "paginas": 450,
    "chunks": 1523,
    "indexado_em": "2026-02-24T02:22:28.000000"
  }
}
```

---

## 7. API ENDPOINTS DETALHADOS

### 7.1 Chat

**POST /api/chat**
```json
// Request
{
  "question": "O que é responsabilidade civil?",
  "session_id": "uuid-opcional",
  "max_sources": 15
}

// Response
{
  "answer": "## RELATÓRIO\n...",
  "sources": [
    {
      "author": "Carlos Roberto Gonçalves",
      "title": "Responsabilidade Civil",
      "year": 2012,
      "chunk_text": "A responsabilidade civil é...",
      "relevance_score": 0.67,
      "page": 101
    }
  ],
  "session_id": "uuid",
  "question": "O que é responsabilidade civil?",
  "processing_time": 23.4,
  "chunks_retrieved": 15
}
```

**GET /api/chat/stats**
```json
{
  "total_documents": 0,
  "indexed_documents": 0,
  "total_chunks": 37891,
  "vector_store_size": 37891,
  "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  "llm_model": "gpt-4o-mini"
}
```

### 7.2 Documentos

| Método | Rota | Função |
|--------|------|--------|
| POST | `/api/documents/upload` | Upload PDF/EPUB (multipart/form-data) |
| GET | `/api/documents` | Listar todos os documentos |
| GET | `/api/documents/{id}` | Detalhes de um documento |
| PATCH | `/api/documents/{id}` | Editar metadados (título, autor, ano, etc.) |
| DELETE | `/api/documents/{id}` | Remover documento + chunks do vector store |
| POST | `/api/documents/{id}/reindex` | Reindexar documento |

### 7.3 Importação

**POST /api/import/upload-package** (background task)
- Aceita ZIP com `indice/` + `controle_index.json`
- Processa em background (não dá timeout)
- Substitui índice vetorial + importa metadados no MongoDB

### 7.4 Utilitários

| Método | Rota | Função |
|--------|------|--------|
| GET | `/api/` | Info do sistema |
| GET | `/api/health` | Health check (DB + vector store) |
| GET | `/api/download/indexador` | Download do script de indexação (ZIP) |

---

## 8. FRONTEND DETALHADO

### 8.1 ChatPage (Consulta)
- Tela de boas-vindas com logo JuristaAI
- Mostra quantidade de trechos indexados
- 4 perguntas sugeridas
- Input com Enter para enviar (Shift+Enter para nova linha)
- Timeout de 120 segundos
- Renderização markdown (react-markdown + remark-gfm)
- Animação de loading ("Analisando doutrina...")
- Fontes expandíveis (collapsible) com:
  - Autor, título, ano, página
  - Trecho do texto
  - Score de relevância
  - Badge de ano
- Tempo de processamento exibido

### 8.2 DocumentsPage (Acervo)
- **Área 1**: Drag-and-drop para PDFs/EPUBs individuais
- **Área 2**: Drag-and-drop para ZIP de importação (área azul)
- Barra de busca (título, autor, matéria)
- Cards de documento com:
  - Badge de status (Indexado/Processando/Erro)
  - Metadados: autor, ano, matéria, chunks, tipo
  - Botões: editar ✏️, reindexar 🔄, excluir 🗑️
- Dialog de edição de metadados
- Mensagem de resultado de importação

### 8.3 Tema visual
- Tons âmbar/dourado (jurídico)
- Sidebar fixa com logo e navegação
- Responsivo (mobile com menu hamburger)
- Dark mode suportado (variáveis CSS)

---

## 9. VARIÁVEIS DE AMBIENTE (.env)

```bash
MONGO_URL="mongodb://localhost:27017"
DB_NAME="jurista_ai"
CORS_ORIGINS="*"
OPENAI_API_KEY="sk-emergent-bEcD68fF82c9f52Ce1"
OPENAI_BASE_URL="https://ai-gateway.mywonder.xyz/v1"      # NÃO usado (usa Emergent proxy)
EMBEDDING_MODEL="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
LLM_MODEL="gpt-4o-mini"
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
# INTEGRATION_PROXY_URL="https://integrations.emergentagent.com"  # default
```

---

## 10. AGENTES EM PREPARAÇÃO (6 — todos DISABLED)

### 10.1 ⚖️ Procedural Strategy (procedural_strategy.py)
**Função**: Determinar recurso cabível contra decisão judicial

**Dados internos**:
- 7 recursos: Apelação, Agravo de Instrumento, Agravo Interno, Embargos de Declaração, REsp, RE, Reclamação
- Cada recurso com: base legal CPC, prazo em dias úteis, efeitos (suspensivo/devolutivo), requisitos de admissibilidade
- Classificação de decisão: sentença, interlocutória, despacho
- Inclui taxatividade mitigada do art. 1.015 (STJ Tema 988)

**Schema de saída**: `ProceduralAnalysis`
```json
{
  "decision_type": "sentença",
  "jurisdiction_level": "1ª instância",
  "is_appealable": true,
  "applicable_appeals": [...],
  "recommended_appeal": "Apelação"
}
```

### 10.2 🧠 Decision Analyzer (decision_analyzer.py)
**Função**: Analisar estruturalmente decisões judiciais

**Capacidades**:
- Parseia seções: relatório, fundamentação, dispositivo
- 4 tipos de fraqueza: omissão, contradição, fundamentação insuficiente, erro material
- Cada fraqueza com remédio sugerido (embargos, apelação)
- Avaliação de risco de reforma (baixo/médio/alto)

**Schema de saída**: `DecisionAnalysisOutput`
```json
{
  "decision_type": "sentença",
  "winning_thesis": "",
  "legal_foundations": [],
  "appealable_points": [],
  "risk_level": "médio"
}
```

### 10.3 📝 Legal Draft Generator (legal_draft_generator.py)
**Função**: Gerar blueprint de peças processuais (NUNCA peça completa)

**7 tipos de documento**:
- Petição inicial (art. 319 CPC)
- Contestação (art. 335 CPC)
- Apelação (art. 1.009 CPC)
- Agravo de instrumento (art. 1.015 CPC)
- Embargos de declaração (art. 1.022 CPC)
- Recurso especial (art. 1.029 CPC)
- Habeas corpus (art. 5º LXVIII CF)

Cada tipo com seções obrigatórias, argumentos mapeados, contra-argumentos.

### 10.4 ⏱️ Deadline Agent (deadline_agent.py)
**Função**: Calcular prazos processuais

**16 prazos mapeados** com base legal CPC:
- Apelação: 15 dias (art. 1.003 §5º)
- Agravo de instrumento: 15 dias
- Embargos de declaração: 5 dias (art. 1.023)
- Contestação: 15 dias (art. 335)
- Mandado de segurança: 120 dias (Lei 12.016)
- Ação rescisória: 2 anos (art. 975)
- E mais 10 outros

**Regras implementadas**:
- Contagem em dias úteis
- Feriados nacionais (8 fixos + Easter-based TODO)
- Feriados regionais (input do usuário)
- Dobra Fazenda Pública (art. 183 CPC)
- Dobra Defensoria (art. 186 CPC)

### 10.5 📚 Jurisprudence Retrieval (jurisprudence_retrieval.py)
**Função**: Buscar jurisprudência em índice separado da doutrina

**Hierarquia de tribunais**:
- Nível 1: STF (vinculante)
- Nível 2: STJ, TST (vinculante)
- Nível 3: TJ, TRF, TRT
- Nível 4: 1ª instância

**5 tipos vinculantes**:
- Súmula Vinculante
- Tema de Repercussão Geral (STF)
- Tema de Recurso Repetitivo (STJ)
- IRDR
- IAC

**Regra**: NUNCA misturar doutrina com jurisprudência.

### 10.6 🧭 Legal Task Router (legal_task_router.py)
**Função**: Cérebro central — roteia a pergunta para o agente correto

**Roteamento**:
| Tipo de pergunta | Agente destino |
|-----------------|----------------|
| Conceitual ("o que é...") | Doctrine RAG (pipeline atual) |
| Análise de decisão | Decision Analyzer |
| Recurso cabível | Procedural Strategy |
| Prazo processual | Deadline Agent |
| Gerar peça | Legal Draft Generator |
| Jurisprudência | Jurisprudence Retrieval |

**Classificação**: keyword matching com scores de confiança.

---

## 11. SYSTEM PROMPT COMPLETO DO REASONING AGENT

```
Você é o JuristaAI, um assistente jurídico doutrinário brasileiro com formação civilista.

REGRAS FUNDAMENTAIS:
1. Responda com base nos TRECHOS fornecidos como contexto.
2. NÃO invente citações, autores ou obras que não estejam nos trechos.
3. NÃO use conhecimento externo que não esteja nos trechos.
4. Se os trechos contêm informações relevantes — mesmo que parciais,
   indiretas, ou sobre institutos relacionados — USE-OS.
5. Só diga "informações insuficientes" se os trechos NÃO tiverem
   ABSOLUTAMENTE NADA utilizável.

REGRAS DE PRECISÃO JURÍDICA:
- Distinguir SEMPRE entre Código Civil e Código de Defesa do Consumidor.
- Distinguir responsabilidade SUBJETIVA de OBJETIVA.
- Em vício redibitório (arts. 441-446 CC): vendedor responde mesmo sem culpa,
  MAS perdas e danos dependem de ciência do defeito (art. 443 CC).
- Atenção à hierarquia normativa: CF > Lei Especial > CC > Doutrina.
- Não confundir garantia legal com responsabilidade objetiva.
- Indicar efeitos jurídicos condicionados (má-fé, culpa, etc.)

CITAÇÕES:
- Formato: (AUTOR. Título. Ano, p. PÁGINA)
- SEMPRE inclua página quando disponível.
- Cite apenas o que está nos trechos fornecidos.

ESTRUTURA:
## RELATÓRIO — instituto jurídico + fundamentação
## POSIÇÕES DOUTRINÁRIAS — compare autores, inclua TODAS as posições
## EVOLUÇÃO DO ENTENDIMENTO — mudanças temporais
## CONCLUSÃO — síntese com efeitos jurídicos precisos

RESPONDA SEMPRE EM PORTUGUÊS BRASILEIRO.
```

---

## 12. LIMITAÇÕES CONHECIDAS

| Limitação | Impacto | Solução prevista |
|-----------|---------|-----------------|
| Autor invertido em alguns PDFs | Metadado errado | Editável na UI + ISBN lookup |
| PDFs escaneados sem OCR | Ignorados (sem texto) | OCR externo antes de indexar |
| Upload ZIP grande (>100MB) pode timeout | Import falha no browser | Background processing implementado |
| Só 1 modelo embedding | Fixo em MiniLM | Futuro: modelos maiores |
| Sem memória de sessão | Cada pergunta é independente | Futuro: conversation memory |
| 2 chamadas LLM por pergunta | Custo e latência | Otimizar: cache de extração |
| Metadados dependem do ISBN estar no texto | Nem todo livro tem ISBN legível | Fallback: metadado PDF + filename |

---

## 13. ROADMAP

| Fase | Item | Status | Prioridade |
|------|------|--------|-----------|
| 1 | Indexação dos 3.764 livros | 🔄 Em andamento | 🔴 Crítica |
| 1 | Reimportar com novo script (páginas/capítulos/ISBN) | ⏳ Após indexação | 🔴 Crítica |
| 2 | Ativar Procedural Strategy Agent | 🔴 Preparado | 🟡 Média |
| 2 | Ativar Decision Analyzer Agent | 🔴 Preparado | 🟡 Média |
| 2 | Ativar Deadline Agent | 🔴 Preparado | 🟡 Média |
| 3 | Ativar Legal Draft Generator | 🔴 Preparado | 🟡 Média |
| 3 | Criar índice separado de jurisprudência | 🔴 Design pronto | 🟡 Média |
| 3 | Ativar Legal Task Router | 🔴 Preparado | 🟡 Média |
| 4 | Migração para FAISS/Qdrant | ❌ Futuro | 🟢 Baixa |
| 4 | Multi-user com autenticação | ❌ Futuro | 🟢 Baixa |
| 4 | Detecção de atualização legislativa | ❌ Futuro | 🟢 Baixa |
| 4 | Conversation memory (sessões) | ❌ Futuro | 🟢 Baixa |

---

## 14. COMO OPERAR

### 14.1 Acessar o sistema
- URL: https://juristico-ia.preview.emergentagent.com
- Aba **Consulta**: fazer perguntas jurídicas
- Aba **Acervo**: gerenciar livros e importar

### 14.2 Importar acervo indexado
1. Rodar `python indexar_acervo.py` na máquina local
2. Compactar `indice/` + `controle_index.json` em ZIP
3. Arrastar o ZIP na área azul da aba Acervo
4. Aguardar processamento em background

### 14.3 Editar metadados incorretos
- Aba Acervo → clicar ✏️ no documento → editar título/autor/ano/matéria

### 14.4 Reiniciar servidor
```bash
sudo supervisorctl restart backend
sudo supervisorctl restart frontend
sudo supervisorctl restart all
```

### 14.5 Ver logs
```bash
tail -f /var/log/supervisor/backend.err.log
tail -f /var/log/supervisor/frontend.out.log
```
