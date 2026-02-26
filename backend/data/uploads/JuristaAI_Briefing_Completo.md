# JURISTAAI — BRIEFING TÉCNICO COMPLETO PARA REVISÃO

## 1. O QUE É

JuristaAI é uma IA jurídica doutrinária brasileira que funciona como **parecerista jurídico digital**. Ingere livros jurídicos (PDF/EPUB), legislação e jurisprudência, indexa semanticamente, e responde perguntas jurídicas com citações verificadas exclusivamente do acervo indexado.

**NÃO é chatbot genérico.** Comporta-se como jurista acadêmico que produz pareceres estruturados.

---

## 2. NÚMEROS ATUAIS

- **3.764 livros** jurídicos indexados (doutrina brasileira)
- **2.168.293 chunks** vetoriais (2.1 milhões)
- **8.118 artigos de lei** indexados (Vade Mecum Senado Federal 2025: CC, CP, CPC, CPP, CDC, CLT, CTN, ECA, CF, Maria da Penha, LEP)
- **~672 súmulas** do STJ extraídas
- **48 arquivos Python** de serviços/agentes
- **~5.000 linhas** de código backend
- **6 agentes ativos** no pipeline
- **6 agentes em preparação** (disabled)

---

## 3. STACK TÉCNICA

| Componente | Tecnologia |
|-----------|-----------|
| Backend | FastAPI (Python 3.11) |
| Frontend | React 19 + Tailwind + shadcn/ui |
| Embeddings | sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384 dims, local) |
| Vector Store | Qdrant (Docker na máquina do usuário, 17.3GB) + LlamaIndex fallback no servidor |
| LLM | OpenAI GPT-4o-mini via Emergent proxy |
| Banco metadados | MongoDB (jurista_ai) |
| Servidor | Kubernetes (15GB RAM, 4 CPU, 10GB /app + 95GB overlay) |
| Máquina local | Ryzen 9, 32GB RAM, Windows (indexação + Qdrant Docker + ngrok) |

---

## 4. PIPELINE RAG COMPLETO (6 estágios ativos)

```
Pergunta do usuário
       │
   [CACHE CHECK] ─── Se hit → resposta instantânea (TTL 1h)
       │
   [0] LEGAL ISSUE EXTRACTOR (LLM)
       │  Decompõe pergunta em JSON:
       │  legal_area, legal_institute, core_questions, keywords_for_retrieval
       │
   [1] VECTOR RETRIEVAL (Qdrant, top 40)
       │  Busca ampla com query aprimorada por keywords
       │
   [2] LEGAL RE-RANKER (in-memory)
       │  40 → 12 chunks curados:
       │  - Boost por matéria (+40%)
       │  - Boost por peso normativo (CF +25%, Lei +10%)
       │  - Boost por artigo referenciado (+20%)
       │  - Diversidade: min 2 autores, max 5 por autor
       │  - Temporal: boost recente, preserva clássicos
       │  - Balanço: garante majoritária + minoritária
       │
   [3] DOCTRINE GRAPH + SYNTHESIZER
       │  - Agrupa chunks por doctrine_id (autor+obra+capítulo)
       │  - Detecta posição doutrinária (majoritária/minoritária/crítica)
       │  - Detecta divergência entre autores
       │  - Detecta evolução entre edições
       │  - Identifica posições minoritárias para preservação
       │  - Sintetiza landscape doutrinário (sem LLM)
       │
   [4] LEGAL APPLICATOR (LLM)
       │  GPT-4o-mini gera parecer estruturado:
       │  RELATÓRIO → FUNDAMENTAÇÃO → POSIÇÕES → APLICAÇÃO → CONCLUSÃO
       │  System prompt: parecerista civilista brasileiro
       │  Regras: só usar trechos fornecidos, preservar minoritárias
       │
   [5] CITATION GUARDIAN
       │  Valida TODAS as citações contra chunks:
       │  - Regex multi-formato extrai citações
       │  - Similaridade ponderada: autor 45%, título 35%, ano 20%
       │  - Citações inválidas flaggeadas [⚠️]
       │
   → RESPOSTA FINAL (cacheada para próximas consultas)
```

---

## 5. METADADOS POR CHUNK

Cada chunk de doutrina contém:
```json
{
  "author": "Carlos Roberto Gonçalves",
  "title": "Responsabilidade Civil",
  "year": 2012,
  "page": 215,
  "capitulo": "CAPÍTULO II - Responsabilidade Objetiva",
  "isbn": "9788502083790",
  "materia": "Direito Civil",
  "posicao_doutrinaria": "majoritaria",
  "fonte_normativa": "doutrina",
  "orgao_julgador": "",
  "artigo_referenciado": "927",
  "peso_normativo": 1,
  "author_id": "a_3f8a2b...",
  "work_id": "w_7c1d4e...",
  "chapter_id": "ch_9b2f1a...",
  "doctrine_id": "d_4e7c8d..."
}
```

---

## 6. HIERARQUIA NORMATIVA IMPLEMENTADA

```
Constituição Federal     peso = 1.00 (5 no ranking)
Súmula Vinculante        peso = 0.98 (4)
Jurisprudência STF       peso = 0.92 (3)
Jurisprudência STJ       peso = 0.90 (3)
Lei Federal              peso = 0.95 (3)
Outros tribunais         peso = 0.85 (2)
Doutrina                 peso = 0.75 (1)
```

---

## 7. SERVIÇOS ATIVOS (17 arquivos)

### Pipeline principal:
| Serviço | Arquivo | Função |
|---------|---------|--------|
| Legal Issue Extractor | legal_issue_extractor.py | Decompõe pergunta em JSON estruturado |
| Vector Service | vector_service.py | Busca vetorial (Qdrant remoto/local + LlamaIndex fallback) |
| Legal Re-Ranker | legal_reranker.py | Re-ranking jurídico (40→12 chunks) |
| Doctrine Graph | doctrine_graph.py | IDs hierárquicos + blocos doutrinários |
| Doctrine Synthesizer | doctrine_synthesizer.py | Sintetiza posições (sem LLM) |
| Doctrine Comparator | doctrine_comparator.py | Compara autores, detecta divergência |
| Reasoning Service | reasoning_service.py | Gera parecer via GPT-4o-mini |
| Citation Guardian | citation_guardian.py | Valida citações pós-geração |
| Chat Service | chat_service.py | Orquestra o pipeline completo |

### Infraestrutura:
| Serviço | Arquivo | Função |
|---------|---------|--------|
| VectorStoreService | vector_store_service.py | Abstração com retry, métricas, health check |
| Semantic Cache | semantic_cache.py | Cache de respostas (TTL 1h, LRU 200) |
| Case Memory | case_memory.py | Memória de caso/processo (MongoDB) |
| Config | config.py | Configuração centralizada DEV/PROD |
| Retrieval Planner | retrieval_planner.py | Decide ordem: Lei → Juris → Doutrina |
| Ingestion Service | ingestion_service.py | Leitura PDF/EPUB |
| Indexing Service | indexing_service.py | Chunking + peso temporal |
| Precedent Graph | precedent_graph.py | Grafo de precedentes (JSON) |

### Serviços especializados (ENABLED=False):
| Serviço | Arquivo | Função |
|---------|---------|--------|
| Jurisprudence Service | jurisprudence_service.py | Busca em jurisprudência |
| Law Service | law_service.py | Busca artigos de lei |

---

## 8. AGENTES EM PREPARAÇÃO (6 — todos DISABLED)

| Agente | Arquivo | Capacidade |
|--------|---------|-----------|
| Procedural Strategy | procedural_strategy.py | 7 recursos CPC mapeados com prazos e efeitos |
| Decision Analyzer | decision_analyzer.py | Parseia sentença (relatório/fundamentação/dispositivo), detecta fraquezas |
| Legal Draft Generator | legal_draft_generator.py | Blueprint de 7 tipos de peças (petição, contestação, apelação...) |
| Deadline Agent | deadline_agent.py | 16 prazos CPC, contagem dias úteis, feriados, dobra Fazenda/Defensoria |
| Jurisprudence Retrieval | jurisprudence_retrieval.py | Hierarquia STF>STJ>TJ, 5 tipos vinculantes |
| Legal Task Router | legal_task_router.py | Roteador central: classifica pergunta → direciona agente |

---

## 9. SCRIPTS DE INDEXAÇÃO LOCAL (9 arquivos)

| Script | Função |
|--------|--------|
| indexar_acervo.py | Indexa livros PDF/EPUB (3.764 livros, 2.1M chunks) |
| indexar_leis.py | Indexa legislação artigo por artigo |
| indexar_jurisprudencia.py | Indexa decisões judiciais (STJ, STF) |
| scraper_leis.py | Baixa leis do planalto.gov.br |
| migrar_para_qdrant.py | Migra LlamaIndex SQLite → Qdrant local |
| migrar_para_server.py | Migra Qdrant local SQLite → Qdrant Server Docker |
| legal_source_classifier.py | Classifica fonte: constituição/lei/jurisprudência/doutrina/súmula |
| jurisprudence_extractor.py | Extrai metadados de decisões (tribunal, relator, ementa) |
| cadastro_magistrados.py | Base de magistrados com tendência decisória |

---

## 10. SYSTEM PROMPT DO PARECERISTA

```
Você é o JuristaAI, parecerista jurídico doutrinário brasileiro.

REGRAS INVIOLÁVEIS:
1. Use APENAS os trechos fornecidos. NÃO use conhecimento externo.
2. NÃO invente citações, autores ou obras.
3. Preservar TODAS as posições doutrinárias (majoritária E minoritária).

PRECISÃO JURÍDICA:
- Distinguir CC vs CDC
- Distinguir responsabilidade subjetiva vs objetiva
- Respeitar hierarquia: CF > Lei Especial > CC > Doutrina
- Indicar efeitos condicionados (má-fé, culpa, etc.)

CITAÇÃO: (AUTOR. Título. Ano, p. PÁGINA)

ESTRUTURA:
## RELATÓRIO
## FUNDAMENTAÇÃO
## POSIÇÕES DOUTRINÁRIAS
## APLICAÇÃO AO CASO
## CONCLUSÃO
```

---

## 11. DETECÇÕES AUTOMÁTICAS NO INDEXADOR

### Posição doutrinária (por chunk):
- **majoritária**: "maioria da doutrina", "entendimento dominante"
- **minoritária**: "parte da doutrina", "há quem sustente"
- **crítica**: "não concordamos", "merece crítica"
- **histórica**: "historicamente", "direito romano"
- **conceito**: "define-se", "consiste em"

### Fonte normativa (por chunk):
- **constituição**: referência direta a dispositivo CF
- **súmula**: "súmula nº..."
- **jurisprudência**: estrutura decisória real (acórdão, relator, julgado em)
- **legislação**: "lei nº", "código civil", CPC, CDC
- **doutrina**: conteúdo acadêmico geral
- **indefinido**: capas, índices, OCR ruim

### Metadados do livro:
- ISBN → Google Books API → Open Library API
- Metadados internos do PDF (fitz.metadata)
- Nome do arquivo ("Autor - Título (Ano).pdf")
- Texto (últimos 3 recursos de fallback)

---

## 12. API ENDPOINTS

| Método | Rota | Função |
|--------|------|--------|
| POST | /api/chat | Pergunta jurídica → parecer |
| GET | /api/chat/stats | Estatísticas |
| POST | /api/documents/upload | Upload PDF/EPUB individual |
| GET | /api/documents | Listar documentos |
| PATCH | /api/documents/{id} | Editar metadados |
| DELETE | /api/documents/{id} | Remover |
| POST | /api/import/upload-package | Importar ZIP |
| POST | /api/upload-large/init | Upload chunked (início) |
| POST | /api/upload-large/chunk | Upload chunked (parte) |
| POST | /api/upload-large/finalize | Upload chunked (finalizar) |
| GET | /api/download/indexador | Baixar scripts |
| GET | /api/health | Health check |

---

## 13. INFRAESTRUTURA

### Servidor (Kubernetes Emergent):
- 15GB RAM, 4 CPU
- /app: 10GB persistente (código + dados pequenos)
- overlay: 95GB (não persistente)
- Backend: FastAPI porta 8001
- Frontend: React porta 3000

### Máquina local do usuário:
- Ryzen 9, 32GB RAM DDR5
- Docker Desktop com Qdrant Server
- ngrok expondo porta 6333
- 2.168.293 chunks no Qdrant local (17.3GB)
- Conexão servidor → Qdrant via ngrok URL

### Fluxo de dados:
```
Servidor (Kubernetes)          Máquina do Usuário (Ryzen 9)
┌─────────────────┐            ┌──────────────────────┐
│ FastAPI          │            │ Qdrant Docker :6333  │
│ React Frontend   │ ←──ngrok──│ 2.1M chunks, 17.3GB  │
│ GPT-4o-mini (API)│            │                      │
│ MongoDB          │            │ Scripts indexação     │
└─────────────────┘            └──────────────────────┘
```

---

## 14. COLLECTIONS QDRANT

| Collection | Conteúdo | Chunks | Status |
|-----------|----------|--------|--------|
| jurista_legal_docs | Doutrina (livros) + Leis | 2.168.293 + 8.118 | Ativo |
| jurista_jurisprudencia | Decisões judiciais | 0 | Preparado |
| jurista_leis | Legislação (separada) | 8.118 | Servidor local |

---

## 15. LIMITAÇÕES CONHECIDAS

1. **Disco servidor**: /app só 10GB → Qdrant roda na máquina do usuário via ngrok
2. **Latência ngrok**: ~100-300ms por query (vs <10ms local)
3. **Sem memória de sessão ativa**: cada pergunta independente (Case Memory preparado mas não integrado)
4. **Metadados parciais**: ~30% dos livros com autor incorreto (PDF sem metadados)
5. **2 chamadas LLM por pergunta**: 1 extractor + 1 parecer (~$0.003 por pergunta)
6. **Sem OCR**: PDFs escaneados sem texto são ignorados
7. **Ngrok free**: URL muda a cada restart

---

## 16. ROADMAP

### Fase 1 (Imediato):
- [ ] Conectar servidor ao Qdrant do usuário via ngrok
- [ ] Indexar súmulas STJ no Qdrant
- [ ] Testar pipeline com 2.1M chunks

### Fase 2 (Curto prazo):
- [ ] Ativar Retrieval Planner (Lei → Juris → Doutrina)
- [ ] Ativar agentes: Deadline, Procedural Strategy
- [ ] Indexar jurisprudência (STJ, STF)
- [ ] Integrar Case Memory no pipeline

### Fase 3 (Médio prazo):
- [ ] Ativar Legal Task Router (cérebro)
- [ ] Ativar Decision Analyzer + Draft Generator
- [ ] Migrar para Qdrant Cloud (eliminar ngrok)
- [ ] Frontend: tela de casos, prazos, peças

### Fase 4 (Longo prazo):
- [ ] Multi-user com autenticação
- [ ] Detecção de atualização legislativa
- [ ] Geração de pareceres completos (PDF)
- [ ] API pública para escritórios
