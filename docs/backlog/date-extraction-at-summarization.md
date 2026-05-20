## Backlog: Date Parsing at Extraction Time

**Context:** ADR-100 currently parses dates at Confluence publish time using LLM. This adds latency to publishing.

**Proposal:** Move date extraction to initial conversation summarization:
- Extract dates during summary generation (LLM already processing text)
- Store date metadata with summary (positions + timestamps)
- Confluence publisher uses pre-extracted dates for ADF chip insertion

**Benefits:**
- Faster publishing (no additional LLM call)
- Dates available for other features (calendar integration, search)
- More accurate context (LLM has full conversation context at extraction time)

**Implementation Notes:**
- Add `extracted_dates` JSON field to stored_summaries table
- Modify summarization prompt to output structured date data
- Update confluence.py to use stored dates instead of calling date_extractor
