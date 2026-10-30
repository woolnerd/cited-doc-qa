# Evals

A small retrieval and answer-quality eval for the live demo. It runs the 31 questions in `dataset.jsonl` through the same search, rerank, and generation steps as `POST /api/query`, using production's models and settings, and scores each stage.

It is a regression check for comparing configurations, not a benchmark. 31 questions written by one person, and graded partly by an LLM, can show that a change helped or hurt. They cannot support a general accuracy claim.

## Dataset

`dataset.jsonl` has one question per line:

- **28 answerable questions** spread across the 9 documents on the live demo (HVAC manual, restaurant SOPs, a services agreement, a commercial lease template, three employee handbooks, and two restaurant operations manuals). Each has a reference answer and one verbatim passage from the source document that answers it.
- **1 question whose answer is blank in the source.** The lease template leaves the late-charge amount empty, so the right answer is that the document doesn't state it.
- **2 questions the documents don't cover** (remote work policy, franchise fee). The right answer is to say so.

The three employee handbooks overlap heavily, so several questions test whether retrieval and the answer stay in the right document.

## Metrics

**Retrieval** (deterministic, over the 29 questions with an expected passage):

- **Candidate hit rate:** the expected passage is somewhere in hybrid search's output (vector + full-text, merged with RRF), before reranking.
- **hit@1 / hit@5 and MRR:** the expected passage's rank in the final context the LLM sees, after reranking and the rerank score threshold.

A chunk counts as a hit only if it comes from the expected document and contains at least half of the expected passage as one contiguous run of words. Punctuation, ligatures, and line breaks are ignored. The half rule lets a passage that straddles a chunk boundary still count.

**Answers** (graded by `anthropic/claude-sonnet-5.5` at temperature 0; answers come from production's `anthropic/claude-haiku-4.5`):

- **Correctness:** correct / partial / incorrect against the reference answer. For uncovered questions, inventing specifics is incorrect.
- **Faithfulness:** the judge lists the answer's factual claims and marks each as supported or not by the retrieved context. The score is supported claims / total claims.
- **Citation validity:** every `[n]` in the answer points to a chunk the model was actually given. This one is deterministic.

## Running it

You need Docker (Colima works), an `OPENROUTER_API_KEY` in `.env`, and the 9 demo PDFs in `sample_documents/real_docs/`. That folder is gitignored; the PDFs are the files listed in `config.chunks_per_document` of any results file.

```bash
# Throwaway pgvector database on port 5433
docker run -d --name cited-doc-qa-eval-db -p 5433:5432 \
  -e POSTGRES_USER=rag_user -e POSTGRES_PASSWORD=evalpass -e POSTGRES_DB=rag_eval \
  pgvector/pgvector:pg16
for f in migrations/0*.sql; do
  docker exec -i cited-doc-qa-eval-db psql -q -U rag_user -d rag_eval < "$f"
done

source venv/bin/activate
python -m evals.run --label current                    # app defaults
python -m evals.run --label baseline --similarity-threshold 0.45
python -m evals.compare baseline current

docker rm -f cited-doc-qa-eval-db                       # when done
```

The first run embeds all 9 documents (about 540 chunks). Later runs reuse them unless the chunk size flags change. A full run takes about 3 minutes and costs well under $1 in OpenRouter calls. `--retrieval-only` skips answering and judging.

Results go to `results/<label>.json`. They hold the summary, the config, and every question's candidates, final context, answer, and judge output. Chunk text is cut to a 200-character preview.

## Results

See [What I measured and what I changed](../README.md#what-i-measured-and-what-i-changed) in the main README.
