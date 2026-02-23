# JuristaAI — Script de Indexação Local

## Pré-requisitos
- Python 3.10 ou superior
- pip instalado

## Instalação

```bash
# Crie um ambiente virtual (recomendado)
python -m venv jurista_env
jurista_env\Scripts\activate   # Windows
# source jurista_env/bin/activate  # Linux/Mac

# Instale as dependências
pip install -r requirements_local.txt
```

## Uso

### 1. Indexar seus livros
```bash
python indexar_acervo.py --pasta "C:\Users\joaop\OneDrive\IA DIREITO"
```

### 2. Opções adicionais
```bash
# Definir tamanho do chunk (padrão: 1000 caracteres)
python indexar_acervo.py --pasta "SUA_PASTA" --chunk-size 1200

# Definir overlap (padrão: 200 caracteres)
python indexar_acervo.py --pasta "SUA_PASTA" --overlap 250

# Processar apenas PDFs
python indexar_acervo.py --pasta "SUA_PASTA" --apenas-pdf

# Processar apenas EPUBs
python indexar_acervo.py --pasta "SUA_PASTA" --apenas-epub

# Retomar indexação interrompida (pula arquivos já processados)
python indexar_acervo.py --pasta "SUA_PASTA" --retomar
```

### 3. Depois de indexar
O script gera uma pasta `jurista_export/` contendo:
- `vectordb/` — banco de vetores ChromaDB
- `metadata.json` — metadados de todos os livros
- `indexacao_log.json` — log de processamento

### 4. Transferir para o servidor
Compacte a pasta `jurista_export/` e faça upload pelo painel do JuristaAI.

Ou envie o arquivo ZIP para o administrador do servidor.

## Tempo estimado
- ~30 chunks/segundo no Ryzen 9
- Livro de 500 páginas: ~2-3 minutos
- Acervo de 36GB (~7000 livros): ~15-20 horas

## Dica
Você pode rodar o script durante a noite. Ele salva o progresso,
então se interromper, basta rodar novamente com `--retomar`.
