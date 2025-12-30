# AI Profile Summaries

## Overview

AI-generated profile summaries for each person based on their message history in the Manila Dialectics Society philosophy discussion group. Summaries auto-regenerate after 30 new messages or can be manually triggered.

## Architecture

```
User clicks "Regenerate" or views stale profile
              │
              ▼
    POST /people/{id}/generate-summary
              │
              ▼
    ┌─────────────────────────┐
    │   Rate Limiter Check    │
    │   (800k tokens/min)     │
    └───────────┬─────────────┘
              │
              ▼
    Fetch ALL messages from person
              │
              ▼
    ┌─────────────────────────┐
    │   Gemini 2.0 Flash      │
    │   Profile Generation    │
    └───────────┬─────────────┘
              │
              ▼
    Update person record with:
    - ai_summary
    - ai_summary_generated_at
    - ai_summary_message_count
              │
              ▼
    Return updated PersonResponse
```

## Database Schema Changes

Add to `people` table:

```sql
ALTER TABLE people ADD COLUMN ai_summary TEXT;
ALTER TABLE people ADD COLUMN ai_summary_generated_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE people ADD COLUMN ai_summary_message_count INTEGER DEFAULT 0;
```

| Column | Type | Description |
|--------|------|-------------|
| `ai_summary` | TEXT | The generated summary text |
| `ai_summary_generated_at` | TIMESTAMP | When summary was last generated |
| `ai_summary_message_count` | INTEGER | Message count at time of generation |

## Dependencies

```
google-genai>=1.0.0  # Google GenAI SDK (not the deprecated google-generativeai)
```

## API Changes

### Modified Endpoints

**GET /people/{person_id}**

Response now includes:
```json
{
  "id": 1,
  "display_name": "John Doe",
  "ai_summary": "John is an active participant who...",
  "ai_summary_generated_at": "2025-12-30T10:00:00Z",
  "ai_summary_stale": false
}
```

- `ai_summary_stale` is `true` when `message_count - ai_summary_message_count >= 30`

### New Endpoints

**POST /people/{person_id}/generate-summary**

Triggers AI summary generation.

Response: Updated `PersonResponse` with new summary

Error responses:
- `429 Too Many Requests` - Rate limit exceeded (800k tokens/min)
- `404 Not Found` - Person not found
- `500 Internal Server Error` - AI service error

## AI Service Details

### Model

- **Model:** `gemini-3-flash-preview`
- **SDK:** Google GenAI SDK (`google-genai`)
- **Thinking Budget:** 712 tokens

### Prompt Template

```
Analyze the following messages from {person_name} in a philosophy discussion group 
called "Manila Dialectics Society". Generate a brief personality profile 
(2-3 paragraphs) covering:

- Communication style and tone
- Topics and themes they discuss most (philosophical or otherwise)
- Notable perspectives or recurring ideas
- Any other interesting patterns

Keep it objective and insightful.

Messages (with timestamps):
{messages}
```

### Message Format

Messages are sent to the AI with timestamps:

```
[2025-12-16 23:47:33] This is an example message about philosophy...
[2025-12-16 23:48:02] Another message discussing dialectics...
```

### Rate Limiting

- **Limit:** 800,000 tokens per minute
- **Implementation:** Sliding window token counter
- **Token estimation:** `len(text) / 4` (rough approximation)
- **Behavior:** Returns 429 error when limit exceeded

## Frontend Changes

### Person Detail Page (`/people/[id]`)

Replace "Coming Soon" placeholder with:

1. **Summary display**
   - Shows AI-generated summary text
   - "Generated X ago" timestamp
   - Stale indicator when 30+ new messages exist

2. **Regenerate button**
   - Triggers POST to generate-summary endpoint
   - Loading spinner during generation
   - Handles rate limit errors gracefully

3. **Empty state**
   - "No summary yet. Click regenerate to create one."

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google AI API key | (required) |

### Docker Compose

```yaml
api:
  environment:
    GEMINI_API_KEY: ${GEMINI_API_KEY}
```

## File Changes

| File | Action |
|------|--------|
| `.env` | Add GEMINI_API_KEY |
| `api/requirements.txt` | Add google-genai |
| `api/src/config.py` | Add gemini_api_key setting |
| `api/src/db.py` | Add 3 columns to Person model |
| `api/src/schemas/person.py` | Add summary fields to response |
| `api/src/services/ai.py` | **New** - Gemini client + rate limiter |
| `api/src/routers/people.py` | Add stale check + generate endpoint |
| `web/src/lib/api.ts` | Add generateSummary method |
| `web/src/app/people/[id]/page.tsx` | Summary UI component |
| `docker-compose.yml` | Add GEMINI_API_KEY env var |

## Auto-Regeneration Logic

Summary is considered **stale** when:
```
current_message_count - ai_summary_message_count >= 30
```

When a profile is viewed with a stale summary:
- UI shows warning: "30+ new messages since last summary"
- User can click to regenerate

This is an **on-demand** approach (vs background jobs) for simplicity.

## Security Considerations

1. **API Key:** Stored in `.env` file, not committed to git
2. **Rate Limiting:** Prevents API abuse and cost overruns
3. **No PII in prompts:** Only display names and message content (already in the group)

## Future Enhancements

- [ ] Batch summary generation for all users
- [ ] Summary comparison over time
- [ ] Topic extraction and tagging
- [ ] Conversation thread analysis
- [ ] Adjustable rate limits via admin UI
