# Performance Testing & Benchmarking

This directory contains performance tests and load tests for the RAG system.

## Test Categories

### 1. Document Processing Benchmarks (`test_document_processing_performance.py`)

Tests document processing performance with various file sizes:
- **Text Extraction**: Small (1 page), Medium (10 pages), Large (50 pages)
- **PDF Extraction**: Small (1 page), Medium (10 pages), Large (50 pages)
- **Chunking**: Various text sizes

### 2. Query Performance Benchmarks (`test_query_performance.py`)

Tests query processing and retrieval performance:
- **Query Processing**: Simple and complex queries
- **Embedding Generation**: Benchmark embedding API calls
- **Reranking**: Benchmark Cohere reranking performance

### 3. Load Tests (`test_load.py`)

Tests system behavior under concurrent load:
- **Concurrent Uploads**: 10 simultaneous document uploads
- **Concurrent Queries**: 50 simultaneous queries
- **Mixed Load**: Combined uploads and queries

### 4. Database Performance (`test_database_performance.py`)

Tests database query performance:
- **Vector Search**: Performance of vector similarity search
- **Full-Text Search**: Performance of PostgreSQL full-text search
- **Hybrid Search**: Combined vector + full-text search
- **Filtered Search**: Document-specific searches
- **Metadata Retrieval**: Document and chunk lookups

## Service Level Objectives (SLOs)

### Query Performance
- **P50 Response Time**: < 1 second
- **P95 Response Time**: < 3 seconds
- **P99 Response Time**: < 5 seconds
- **Availability**: 99% of queries succeed

### Document Processing
- **Small Documents (1 page)**: < 2 seconds
- **Medium Documents (10 pages)**: < 10 seconds
- **Large Documents (50 pages)**: < 60 seconds

### Concurrent Operations
- **10 Concurrent Uploads**: ≥ 70% success rate
- **50 Concurrent Queries**: ≥ 90% success rate
- **Query Throughput**: > 5 queries/second

### Database Operations
- **Vector Search**: < 200ms average
- **Full-Text Search**: < 100ms average
- **Hybrid Search**: < 300ms average
- **Metadata Retrieval**: < 50ms average

## Running Tests

### Run All Performance Tests
```bash
pytest tests/performance/ -v --benchmark-only
```

### Run Specific Test Suite
```bash
# Document processing benchmarks
pytest tests/performance/test_document_processing_performance.py --benchmark-only

# Query benchmarks
pytest tests/performance/test_query_performance.py --benchmark-only

# Load tests
pytest tests/performance/test_load.py -v

# Database benchmarks
pytest tests/performance/test_database_performance.py --benchmark-only
```

### Run Load Tests Only
```bash
pytest tests/performance/ -m slow -v
```

### Generate Benchmark Report
```bash
pytest tests/performance/ --benchmark-only --benchmark-save=baseline
```

### Compare Against Baseline
```bash
pytest tests/performance/ --benchmark-only --benchmark-compare=baseline
```

### View Benchmark Statistics
```bash
pytest tests/performance/ --benchmark-only --benchmark-columns=min,max,mean,stddev,median,rounds,iterations
```

## Benchmark Output

pytest-benchmark provides detailed statistics for each test:
- **Min/Max**: Minimum and maximum execution times
- **Mean**: Average execution time
- **StdDev**: Standard deviation
- **Median**: Median execution time (P50)
- **Rounds**: Number of test rounds executed
- **Iterations**: Number of iterations per round

## Performance Monitoring

### Key Metrics to Monitor
1. **Response Time Percentiles** (P50, P95, P99)
2. **Throughput** (requests per second)
3. **Error Rate** (failed requests / total requests)
4. **Database Query Latency**
5. **Memory Usage** (during document processing)

### Known Bottlenecks

Based on testing, the following components are performance-critical:

1. **Vector Embedding Generation**
   - External API call to Google Gemini
   - ~200-500ms per request
   - Consider batching for large documents

2. **PDF Text Extraction**
   - Large PDFs (>50 pages) can take 10+ seconds
   - Consider async processing queue for large files

3. **Database Vector Search**
   - Performance degrades with > 100k chunks
   - IVFFlat index requires optimization for large datasets
   - Consider adding partition key on document_id

4. **LLM Generation**
   - External API call to OpenRouter/Claude
   - ~1-3 seconds per query
   - Response time varies with prompt length

5. **Reranking Service**
   - Cohere API latency ~100-300ms
   - Scales linearly with number of documents
   - Consider caching for repeated queries

## Optimization Recommendations

### Short-term (< 1 week)
1. **Add caching** for repeated queries
2. **Batch embeddings** for document processing
3. **Optimize chunk size** (currently 512 tokens)

### Medium-term (1-4 weeks)
1. **Implement async document processing** with Celery
2. **Add database indexes** for common query patterns
3. **Optimize IVFFlat parameters** based on data size

### Long-term (> 1 month)
1. **Implement CDN** for frequently accessed documents
2. **Add read replicas** for database scaling
3. **Consider pgvector alternatives** (e.g., Pinecone, Weaviate)

## Continuous Performance Testing

### CI/CD Integration
Performance tests run automatically on:
- Pull requests (quick benchmarks only)
- Main branch commits (full benchmark suite)
- Nightly builds (comprehensive load tests)

### Regression Detection
Tests will fail if:
- P95 query time exceeds 3 seconds
- Concurrent query success rate < 90%
- Database operations exceed baseline by > 50%

## Testing Best Practices

1. **Run on consistent hardware** for reliable benchmarks
2. **Warm up database** before running tests
3. **Use realistic data sizes** matching production workload
4. **Test under various load conditions**
5. **Monitor system resources** (CPU, memory, disk I/O)
6. **Run multiple iterations** to account for variance

## Further Reading

- [pytest-benchmark documentation](https://pytest-benchmark.readthedocs.io/)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [pgvector Optimization Guide](https://github.com/pgvector/pgvector#performance)
