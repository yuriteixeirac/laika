# Laika

API RAG baseada na bibliografia do curso técnico em informática do IFRN Campus Ceará-Mirim.

## Requisitos

- Python `>=3.13`
- PostgreSQL com a extensão `vector`
- `uv`

## Configuração

```bash
uv sync
cp .env.example .env
```

Preencha no `.env` a chave da aplicação, a conexão com o banco e as credenciais do SUAP.

## Uso

Inicie o servidor:

```bash
uv run fastapi dev app
```

Aplique as migrações:

```bash
uv run alembic upgrade head
```

Para ingerir os PDFs, coloque-os em `data/raw/` e execute:

```bash
uv run python -m scripts.ingestion
```

Arquivos já ingeridos são identificados pelo hash SHA-256 e pulados. Para
re-ingerir (por exemplo, após trocar o modelo de embedding), use:

```bash
uv run python -m scripts.ingestion --force
```

## Testes

```bash
uv run pytest
```
