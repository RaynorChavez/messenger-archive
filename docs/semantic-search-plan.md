# Semantic Search Service - Implementation Plan

## Overview

Add vector-based semantic search across messages, discussions, people, and topics using Gemini's `text-embedding-004` model and PostgreSQL's `pgvector` extension.

## Current State

| Entity | Count | What to Embed |
|--------|-------|---------------|
| Messages | ~6,000 | `content` |
| Discussions | ~183 | `title + summary` |
| People | ~77 | `display_name + summary` |
| Topics | ~9 | `name + description` |

**Existing search:** PostgreSQL full-text search (`to_tsvector`) on messages only.

---

## Design Decisions

| Decision | Choice |
|----------|--------|
| Search type | Hybrid (semantic + keyword), alpha = 0.5 |
| Default scope | All (grouped by entity type) |
| Similarity threshold | 0.3 minimum |
| Semantic-only matches | Yes, included |
| Reindex trigger | Button in Settings page |
| New message embedding | Immediate (in archive-service) |

---

## Hybrid Scoring Logic

```python
# For each entity:
semantic_score = 1 - cosine_distance(embedding, query_embedding)
keyword_score = ts_rank(to_tsvector(content), plainto_tsquery(query))  # normalized 0-1

# Combine with alpha
if has_keyword_match:
    final_score = 0.5 * semantic_score + 0.5 * keyword_score
else:
    final_score = semantic_score  # semantic-only match

# Filter
if final_score < 0.3:
    exclude from results
```

---

## Implementation Phases

### Phase 1: Database Setup

| Task | File | Description |
|------|------|-------------|
| 1.1 | `docker-compose.yml` | Change `postgres:15-alpine` -> `pgvector/pgvector:pg15` |
| 1.2 | `scripts/init-db.sql` | Add `CREATE EXTENSION vector` and `embeddings` table |
| 1.3 | `scripts/migrate-pgvector.sql` | Migration script for existing DBs |
| 1.4 | `api/requirements.txt` | Add `pgvector` package |
| 1.5 | `api/src/db.py` | Add `Embedding` SQLAlchemy model |

### Phase 2: Embedding Service

| Task | File | Description |
|------|------|-------------|
| 2.1 | `api/src/services/embeddings.py` | **New** - EmbeddingService class |
| 2.2 | `api/src/services/__init__.py` | Export embedding service |

**EmbeddingService features:**
- `embed_text(text)` - single text embedding
- `embed_batch(texts)` - batch up to 100 texts per API call
- `get_content_hash(text)` - SHA256 for change detection
- Reuses `TokenBucket` rate limiter
- Model: `text-embedding-004` (768 dimensions)

### Phase 3: Search API

| Task | File | Description |
|------|------|-------------|
| 3.1 | `api/src/routers/search.py` | **New** - `GET /api/search` endpoint |
| 3.2 | `api/src/routers/__init__.py` | Export search router |
| 3.3 | `api/src/main.py` | Include search router |

**Endpoint:**
```
GET /api/search?q=<query>&scope=all|messages|discussions|people|topics&limit=20
```

**Response format:**
```json
{
  "query": "philosophy of mind",
  "results": {
    "messages": [
      {
        "id": 123,
        "content": "The hard problem of consciousness...",
        "sender": {"id": 5, "display_name": "John"},
        "timestamp": "2025-12-20T14:30:00Z",
        "score": 0.87,
        "match_type": "hybrid"
      }
    ],
    "discussions": [...],
    "people": [...],
    "topics": [...]
  },
  "counts": {
    "messages": 15,
    "discussions": 3,
    "people": 2,
    "topics": 1,
    "total": 21
  }
}
```

### Phase 4: Reindex API & Settings UI

| Task | File | Description |
|------|------|-------------|
| 4.1 | `api/src/routers/search.py` | Add `POST /api/search/reindex` endpoint |
| 4.2 | `api/src/routers/search.py` | Add `GET /api/search/status` for progress |
| 4.3 | `web/src/app/settings/page.tsx` | Add "Reindex Search" button |
| 4.4 | `web/src/lib/api.ts` | Add search reindex API methods |

**Reindex endpoint:**
```
POST /api/search/reindex?scope=all|messages|discussions|people|topics
```

**Status endpoint:**
```
GET /api/search/status
{
  "status": "running",
  "progress": {
    "messages": {"total": 5926, "completed": 2500},
    "discussions": {"total": 183, "completed": 183}
  },
  "last_completed_at": "2025-12-31T..."
}
```

### Phase 5: Frontend Search UI

| Task | File | Description |
|------|------|-------------|
| 5.1 | `web/src/app/search/page.tsx` | Rewrite with semantic search UI |
| 5.2 | `web/src/lib/api.ts` | Add search types and API methods |

**UI Components:**
- **Scope tabs:** All | Messages | Discussions | People | Topics
- **Result cards** (distinct per type):
  - Message: avatar, sender name, content snippet, timestamp, score bar
  - Discussion: title, summary snippet, date range, message count
  - Person: avatar, name, summary snippet
  - Topic: colored badge, name, description
- **Score indicator:** Small bar or percentage showing match strength
- **Match type badge:** "Semantic" or "Hybrid" indicator

### Phase 6: Archive Service Integration

| Task | File | Description |
|------|------|-------------|
| 6.1 | `archive-service/src/main.py` | Call embedding API on new message |
| 6.2 | `api/src/routers/search.py` | Add `POST /api/search/embed` endpoint |

---

## File Changes Summary

| File | Status | Changes |
|------|--------|---------|
| `docker-compose.yml` | Modify | postgres image -> pgvector |
| `scripts/init-db.sql` | Modify | Add vector extension + embeddings table |
| `scripts/migrate-pgvector.sql` | **New** | Migration for existing DB |
| `api/requirements.txt` | Modify | Add `pgvector` |
| `api/src/db.py` | Modify | Add `Embedding` model |
| `api/src/services/embeddings.py` | **New** | EmbeddingService class |
| `api/src/services/__init__.py` | Modify | Export embeddings |
| `api/src/routers/search.py` | **New** | Search + reindex endpoints |
| `api/src/routers/__init__.py` | Modify | Export search router |
| `api/src/main.py` | Modify | Include search router |
| `web/src/lib/api.ts` | Modify | Add search types + methods |
| `web/src/app/search/page.tsx` | Rewrite | Semantic search UI |
| `web/src/app/settings/page.tsx` | Modify | Add reindex button |
| `archive-service/src/main.py` | Modify | Embed on message store |

---

## Migration (Preserve Existing Data)

The pgvector image is a drop-in replacement - same postgres version, just with the extension pre-installed. Existing data volume remains intact.

```bash
# 1. Backup current database
docker compose exec postgres pg_dump -U archive -d messenger_archive > backup_$(date +%Y%m%d).sql

# 2. Stop services
docker compose down

# 3. Update docker-compose.yml (change postgres image)
# postgres:15-alpine -> pgvector/pgvector:pg15

# 4. Start only postgres with new image
docker compose up -d postgres

# 5. Run migration script
docker compose exec postgres psql -U archive -d messenger_archive -f /docker-entrypoint-initdb.d/migrate-pgvector.sql

# 6. Start all services
docker compose up -d
```

---

## Cost Estimate

Gemini embedding pricing: ~$0.00001/1K characters

- ~6,000 messages x avg 100 chars = 600K chars ~ $0.006
- ~183 discussions x avg 500 chars = 91K chars ~ $0.001
- ~77 people x avg 500 chars = 38K chars ~ $0.0004
- ~9 topics x avg 200 chars = 1.8K chars ~ $0.00002

**Total: < $0.01** for full reindex

---

## Estimated Effort

| Phase | Tasks | Time |
|-------|-------|------|
| Phase 1: Database | 5 | 15 min |
| Phase 2: Embedding Service | 2 | 30 min |
| Phase 3: Search API | 3 | 45 min |
| Phase 4: Reindex API + Settings | 4 | 30 min |
| Phase 5: Frontend Search | 2 | 45 min |
| Phase 6: Archive Integration | 2 | 15 min |
| **Total** | **18** | **~3 hours** |
