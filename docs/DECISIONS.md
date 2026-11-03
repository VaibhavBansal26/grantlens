# Technical decisions

## Which models and services are used

| Job | What | Where it runs |
|---|---|---|
| Text embeddings (semantic search, matching, document passages) | `BAAI/bge-small-en-v1.5`, 384 dimensions | Weights from the **Hugging Face Hub**, run **locally** on CPU through `sentence-transformers` (baked into the API image) |
| Optional reranking (tested, **off by default**) | `cross-encoder/ms-marco-MiniLM-L-6-v2`, `BAAI/bge-reranker-base` | Hugging Face Hub, local. Neither beat plain hybrid search on the labelled set. |
| Writing: document answers, fit check, review builder, search-query writing, the evaluation judge | `gpt-4o-mini` (`OPENAI_MODEL`) | **OpenAI's API**, behind the small `LLM` interface in `llm.py` |
| Paper metadata and abstracts | OpenAlex | Public API |
| Vector and keyword search, all data | Postgres 16 with pgvector (HNSW) plus an in-process BM25 index | Self-hosted container |

Optional, tested but not the default: Llama 3.1 8B through Hugging Face Inference Providers (`LLM_BACKEND=hf`); see `LLAMA_COMPARISON.md`.
Not used: Hugging Face Spaces, Pinecone, Vertex AI. Nothing in this build is fine-tuned.

## Why pgvector and not Pinecone

The corpus is about 84,000 opportunities and 75,000 awards at 384 dimensions, roughly 130 MB of vectors. At that size a
dedicated vector database adds cost, a second place where data lives, another API key and a network hop, and gives
nothing back. Keeping vectors in Postgres means one query can combine meaning with the filters people actually use
(status, agency, close date, amount), vectors are part of every backup and restore (tested), and a deleted account's data
goes in one place. The price: filtered HNSW search needed tuning (`hnsw.iterative_scan`, found when recall dropped), and
scaling past tens of millions of vectors would mean revisiting this. Search is in `retrieval/dense.py` and
`retrieval/lexical.py`; moving to a managed vector store would mean writing an adapter for `dense.py`.

## Why no Llama (and no fine-tuning)

- **The roadmap made fine-tuning conditional** ("only if the evaluation shows it helps"), and the evaluation did not call for it:
  the hosted model scores well on the measurable tasks (see `AI_QUALITY.md`), while the weaknesses found were fixed by
  checking the model's output in code, which a fine-tune would not replace.
- **No hardware for it here.** This was built on a laptop with no GPU. Fine-tuning a Llama-class model, or serving one at
  useful speed for several users, needs a GPU machine or a paid hosted endpoint.
- **No training data for a generation task.** There are 84,000 grants but no labelled examples of "good answers" to fine-tune on.
  The more promising fine-tune is the *embedding* model, using the labelled search pairs; it is measurable with the
  existing ablation harness, and not done yet.
- **A Llama backend was then built and measured** (the `LLM` interface made it a contained change): it matches gpt-4o-mini at reading but is worse
  at declining, at structure and at speed, so it is optional and not the default. Results: `LLAMA_COMPARISON.md`.

Note on the resume: the Llama fine-tuning and Pinecone described for the CUBS project are not part of this rebuild. This repository
contains none of that work, so describe each project for what it actually contains.
