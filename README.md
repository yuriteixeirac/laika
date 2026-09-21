# Laika

Assistente de estudos com RAG sobre a bibliografia do curso técnico em informática do IFRN Campus Ceará-Mirim.

O Laika responde perguntas de alunos usando **apenas** os PDFs previamente ingeridos da bibliografia do curso. Cada resposta é montada a partir de trechos recuperados do corpus e o prompt instrui o modelo a citar documento e página — ou a admitir que não encontrou a informação, em vez de inventar.

---

## Sobre o projeto

O problema que o projeto ataca é simples: a bibliografia de um curso técnico é extensa, espalhada em PDFs e pouco consultável. Um aluno que quer relembrar "o que é um laço de repetição" precisa abrir dezenas de arquivos. Um chatbot genérico responde, mas com conhecimento próprio — e não com o material que o professor adotou.

O Laika fecha essa lacuna com três decisões de projeto:

1. **Grounding restrito.** Só o que está na bibliografia ingerida entra no contexto. Se nada relevante for recuperado, a resposta é "não encontrei na bibliografia".
2. **Rastreabilidade.** O prompt exige citação de documento e página, para o aluno poder conferir a fonte.
3. **Acesso institucional.** O login é feito pelo SUAP, então o uso fica vinculado à matrícula e cada aluno só enxerga as próprias sessões.

O que o projeto **não** é: não é um tutor que resolve exercícios do zero, nem um índice de busca full-text, nem um sistema de gestão de conteúdo. Ele responde a partir do corpus — e o corpus é curado manualmente.

---

## Como funciona

### Ingestão (offline, sob demanda)

```
data/raw/*.pdf
     │
     ├─ PyMuPDF extrai o texto de cada página
     ├─ chunk_page() quebra em janelas de 300 caracteres com 50 de overlap
     ├─ embed_passagens() gera vetores de 768 dims  (prefixo "passage: ")
     └─ Chunk(conteudo, embedding, pagina, versao_embedding) → PostgreSQL/pgvector
```

Cada `Documento` guarda o SHA-256 do PDF, então rodar a ingestão duas vezes não duplica nada.

### Consulta (online, com streaming)

```
POST /chat/{id}
     │
     ├─ histórico da sessão (mensagens em ordem cronológica)
     ├─ condensar_consulta() reescreve follow-ups usando o histórico
     ├─ embed_consulta() gera o vetor da pergunta  (prefixo "query: ")
     ├─ pgvector: top-3 por distância de cosseno, acima do limiar e da versão atual
     ├─ montar_mensagens() = prompt de sistema com contexto + histórico
     └─ DeepSeek (stream=True) → SSE → navegador
```

---

## Stack

| Camada | Escolha |
|---|---|
| API | FastAPI + Uvicorn (`fastapi[standard]`) |
| Persistência | PostgreSQL + pgvector, SQLAlchemy 2.0 async, driver `asyncpg` |
| Migrações | Alembic (conexão assíncrona) |
| Embeddings | `intfloat/multilingual-e5-base` (768 dims), via `sentence-transformers` |
| LLM | `deepseek-v4-flash`, via cliente `openai` (API compatível) |
| Autenticação | OAuth2 do SUAP, via Authlib; sessão em cookie assinado |
| Empacotamento | `uv` (Python `>=3.13`) |
| Testes | pytest + pytest-asyncio (suíte hermética) |

---

## Requisitos

- Python `>=3.13`
- [`uv`](https://docs.astral.sh/uv/)
- PostgreSQL com a extensão **`vector`** (pgvector). A primeira migração cria a extensão, então basta que ela esteja disponível na imagem.

Se você não tem um Postgres com pgvector à mão:

```bash
docker run -d --name laika-db -p 5432:5432 \
  -e POSTGRES_USER=laika -e POSTGRES_PASSWORD=laika -e POSTGRES_DB=laika \
  pgvector/pgvector:pg17
```

---

## Configuração

```bash
uv sync
cp .env.example .env
```

Preencha o `.env`:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `SECRET_KEY` | sim | Assina o cookie de sessão. Gere com `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `SQLALCHEMY_DATABASE_URI` | sim | **Precisa** do driver async: `postgresql+asyncpg://usuario:senha@host:5432/banco`. |
| `SUAP_CLIENT_ID` | sim | Credenciais do aplicativo OAuth registradas no SUAP. |
| `SUAP_CLIENT_SECRET` | sim | Idem. |
| `DEEPSEEK_API_KEY` | sim | Chave da API da DeepSeek. |
| `RAG_DISTANCIA_MAXIMA` | não | Distância de cosseno máxima para um trecho entrar no contexto. Padrão `0.40`. |

Em seguida, aplique as migrações:

```bash
uv run alembic upgrade head
uv run alembic current   # confirma a revisão aplicada
```

---

## Ingestão da bibliografia

Coloque os PDFs em `data/raw/` (o diretório não é versionado) e rode:

```bash
uv run python -m scripts.ingestion
```

O script:

- calcula o SHA-256 de cada PDF e **pula** o que já está no banco;
- extrai o texto página a página, gera os embeddings em lote e grava os chunks;
- registra cada falha no log e continua com os próximos arquivos;
- termina com `exit code 1` se algum arquivo falhou (útil em cron/CI).

Para re-ingerir arquivos já presentes — apagando os chunks antigos antes:

```bash
uv run python -m scripts.ingestion --force
```

### ⚠️ Ao mudar o contrato de embedding

O modelo, os prefixos e a versão ficam em `app/utils.py` (`MODELO_EMBEDDING`, `E5_QUERY_PREFIX`, `E5_PASSAGE_PREFIX`, `ESQUEMA_EMBEDDING`, `VERSAO_EMBEDDING`). O retrieval filtra por `Chunk.versao_embedding`, então **trocar qualquer um desses valores exige re-ingerir o corpus**:

```bash
uv run python -m scripts.ingestion --force
```

Sem isso, todos os vetores antigos são ignorados e o assistente responde "não encontrei na bibliografia" para qualquer pergunta. Essa falha é intencional: é melhor ficar evidente do que devolver respostas baseadas em vetores incompatíveis.

### PDFs escaneados

A extração usa a camada de texto do PDF. Arquivos sem texto (digitalizações) geram zero chunks — o script emite um aviso `nenhum texto extraído (PDF escaneado?)` no log. **OCR não está implementado**; esses documentos precisam ser processados antes.

---

## Rodando a API

```bash
uv run fastapi dev app
```

A documentação interativa fica em `http://127.0.0.1:8000/docs`.

---

## Endpoints

Todas as rotas de `/sessao` e `/chat` exigem login; sem sessão válida respondem `401`.

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/auth/suap/login` | Redireciona para o SUAP. |
| `GET` | `/auth/suap/callback` | Troca o código, cria/atualiza o usuário e abre a sessão. |
| `POST` | `/auth/logout` | Encerra a sessão. |
| `GET` | `/sessao/` | Lista as sessões do usuário logado. |
| `GET` | `/sessao/{id}` | Detalhe de uma sessão. |
| `PUT` | `/sessao/{id}` | Renomeia a sessão. |
| `DELETE` | `/sessao/{id}` | Apaga a sessão. |
| `GET` | `/sessao/{id}/mensagens` | Histórico da sessão. |
| `POST` | `/chat/` | Cria a sessão, envia a primeira pergunta e responde em streaming. |
| `POST` | `/chat/{sessao_id}` | Continua uma sessão existente, em streaming. |

Payload de ambos os endpoints de chat:

```json
{ "conteudo": "o que é um laço de repetição?" }
```

### Formato do streaming

As respostas usam **Server-Sent Events**. `POST /chat/` emite um evento `meta` com o id da sessão criada (o front usa isso para redirecionar) e um evento `done` com o título gerado:

```
event: meta
data: {"session_id": 12, "redirect": "/chat/12"}

data: {"delta": "Um "}
data: {"delta": "laço "}
data: {"delta": "repete um bloco."}

event: done
data: {"title": "Laços de repetição"}
```

`POST /chat/{sessao_id}` emite `meta` e `done` sem payload (a sessão e o título já existem). O texto completo é persistido como `Mensagem` do tipo `assistant` quando o stream termina.

Exemplo com `curl` (reaproveitando um cookie de sessão autenticado):

```bash
curl -N -X POST http://127.0.0.1:8000/chat/ \
  -H 'Content-Type: application/json' \
  -b cookies.txt \
  -d '{"conteudo": "o que é um laço de repetição?"}'
```

---

## Como o RAG decide o contexto

| Etapa | Implementação |
|---|---|
| Chunking | `chunk_page()`: janelas de 300 caracteres com 50 de overlap de cada lado. |
| Prefixos do E5 | `passage: ` na ingestão, `query: ` na busca. O E5 foi treinado com essa assimetria; omiti-la degrada a similaridade. |
| Busca | Distância de cosseno no pgvector (`<=>`) sobre vetores normalizados, com índice **HNSW** (`vector_cosine_ops`). |
| Quantidade | Top-3 (`RAG_TOP_K`). |
| Limiar | Só entram trechos com distância `< RAG_DISTANCIA_MAXIMA`. Sem isso, ferramentas irrelevantes entrariam no contexto de qualquer pergunta. |
| Versionamento | Filtro por `versao_embedding`, que impede misturar vetores de modelos diferentes. |
| Follow-ups | `condensar_consulta()` reescreve "e em Python?" em uma consulta autônoma antes de buscar. É pulado no primeiro turno da sessão, e cai na pergunta original se a LLM falhar. |
| Prompt | `PROMPT_SISTEMA_RAG`: responder só com o contexto, citar documento e página, e admitir quando não encontrar. |

O histórico completo da sessão é enviado em todas as chamadas — o contexto recuperado, porém, é recalculado a cada pergunta.

---

## Testes

```bash
uv run pytest
```

São **57 testes**, com `asyncio_mode = "auto"` configurado no `pyproject.toml`. A suíte é **hermética**: não abre conexão com PostgreSQL nem com a API da DeepSeek. O `AsyncSession` é substituído por um duplo (`tests/helpers.py`) injetado via `dependency_overrides`, o cliente OpenAI por um dublê que faz streaming de deltas controlados, e o modelo de embedding nunca é carregado.

| Arquivo | Cobertura |
|---|---|
| `tests/test_utils.py` | Autenticação, título, histórico, montagem do prompt, condensação, formatação do contexto, retrieval (prefixos, limiar, versão) e embeddings. |
| `tests/test_chat_router.py` | Ambos os endpoints de chat: retrieval, streaming SSE, persistência, follow-up condensado e falha no meio do stream. |
| `tests/test_sessao_router.py` | CRUD de sessões, listagem de mensagens e rotas protegidas. |
| `tests/test_auth_router.py` | Login, callback do SUAP (usuário novo e existente), sessão e logout. |
| `tests/test_ingestion.py` | Hash, idempotência, `--force`, PDF sem texto e contagem de falhas. |

---

## Estrutura do projeto

```
app/
├── __init__.py          # instancia o FastAPI, o engine async, o OAuth do SUAP e inclui os routers
├── utils.py             # contrato de embedding, retrieval, prompt, auth e helpers de sessão
├── models/              # Usuario, Sessao, Mensagem, Documento, Chunk
├── routers/             # auth_router, sessao_router, chat_router
└── schemas/             # payloads Pydantic
scripts/
└── ingestion.py         # ingestão dos PDFs de data/raw/
alembic/versions/        # extensão vector, tabelas, índice HNSW, hash e versão do embedding
tests/                   # suíte hermética
data/raw/                # PDFs da bibliografia (não versionados)
```

---

## Limitações conhecidas

Coisas que ainda faltam e que vale saber antes de usar em produção:

- **As fontes não chegam ao cliente.** O stream manda apenas `delta` e `title`; o aluno não consegue clicar e abrir o PDF na página citada. É a lacuna de maior impacto na experiência de estudo.
- **O limiar não está calibrado.** `RAG_DISTANCIA_MAXIMA=0.40` é um ponto de partida; o E5 comprime as similaridades perto de 1. Sem um conjunto de avaliação (perguntas e respostas esperadas), não há como ajustar isso nem medir o efeito de mudanças no chunking.
- **Conteúdo dos PDFs entra como prompt de sistema.** Um documento com texto malicioso poderia tentar instruir o modelo. O contexto deveria ser delimitado e tratado como dado.
- **Falha da LLM persiste mensagem vazia.** O bloco `finally` grava o texto acumulado mesmo que o stream morra antes do primeiro delta.
- **Busca apenas densa.** Sem BM25/híbrida, termos exatos, siglas e códigos de disciplina recuperam mal.
- **Chunking ingênuo.** Janelas fixas de 300 caracteres cortam no meio de palavras e não respeitam parágrafos nem seções.
- **Sem OCR**, sem extração de tabelas e figuras.
- **Sem observabilidade**: sem logging estruturado, métricas, tracing ou contabilização de tokens.
- **Modelo de embedding no processo da API.** Cada worker carrega sua própria cópia do torch (memória alta, primeira requisição lenta). Em escala, o caminho é um serviço de embeddings separado.
- **Sem rate limit, moderação ou papéis de acesso** — qualquer usuário do SUAP autenticado enxerga todo o corpus.
- **Sem paginação** em sessões e mensagens; **sem CORS**, healthcheck ou `https_only` no cookie de sessão.
- **Histórico sem limite**: sessões longas tendem a estourar a janela de contexto do modelo.

---

## Aviso

Os PDFs da bibliografia **não são versionados** (`data/raw/` está no `.gitignore`) e os direitos autorais pertencem aos respectivos autores e editoras. O `.env` também não é versionado. Como o histórico de conversas é dado pessoal vinculado à matrícula, qualquer implantação real precisa de uma política de retenção e de um canal para o aluno solicitar a exclusão dos seus dados.
