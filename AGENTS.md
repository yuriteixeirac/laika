# Instruções do repositório

## Ambiente

- Use Python `>=3.13`.
- Use `uv` para instalar dependências e executar comandos; mantenha o `uv.lock` atualizado quando as dependências mudarem.
- Prepare o ambiente com `uv sync`.
- Crie `.env` a partir de `.env.example`. A aplicação espera `SECRET_KEY`, `SQLALCHEMY_DATABASE_URI`, `SUAP_CLIENT_ID` e `SUAP_CLIENT_SECRET`.
- Não versione `.env` nem os PDFs em `data/raw/`.

## Estrutura

- `app/` contém a aplicação FastAPI, os modelos SQLAlchemy e as rotas.
- O objeto FastAPI se chama `app` e fica em `app/__init__.py`; não existe `main.py`.
- `app/models/` define as entidades e `alembic/env.py` importa o `Base` para autogeração de migrações.
- `scripts/ingestion.py` ingere os PDFs de `data/raw/`, gera embeddings com `intfloat/multilingual-e5-base` e grava os chunks no PostgreSQL. Arquivos já ingeridos são identificados pelo hash SHA-256; use `--force` para re-ingerir.
- O contrato de embedding (modelo, prefixos `query:`/`passage:` e `VERSAO_EMBEDDING`) fica em `app/utils.py`. Ao alterá-lo, re-ingira o corpus: o retrieval só considera chunks da versão atual.

## Comandos

- Servidor local: `uv run fastapi dev app`.
- Aplicar todas as migrações: `uv run alembic upgrade head`.
- Verificar a revisão atual: `uv run alembic current`.
- Criar uma migração após alterar os modelos: `uv run alembic revision --autogenerate -m "descricao"`.
- Executar a ingestão: `uv run python -m scripts.ingestion` (use `--force` para re-ingerir PDFs já presentes).
- Rodar os testes: `uv run pytest`.

## Banco e migrações

- As migrações usam conexão assíncrona e leem `SQLALCHEMY_DATABASE_URI` do `.env`.
- O banco precisa ser PostgreSQL com suporte à extensão `vector`; a primeira migração cria essa extensão.
- Revise migrações autogeradas antes de aplicá-las, especialmente alterações de índices e tipos PostgreSQL.

## Verificação

- Há uma suíte de testes em `tests/` (pytest + pytest-asyncio), hermética: não acessa PostgreSQL nem a API da DeepSeek. Não há CI, lint ou formatter configurados.
- Após alterações, valide pelo menos a importação da aplicação, o comando diretamente relacionado à mudança ou `uv run pytest`.
