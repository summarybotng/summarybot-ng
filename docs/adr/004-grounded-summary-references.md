# ADR-004: Grounded Summary References — Citing Conversation Sources

**Status:** Proposed
**Date:** 2026-02-11
**Depends on:** ADR-002 (Ingest Adapter), ADR-003 (SummaryBot-NG Modifications)
**Repository:** [summarybotng/summarybot-ng](https://github.com/summarybotng/summarybot-ng)

---

## 1. Problem Statement

Today, SummaryBot-NG produces summaries that make claims about what was said but provide **no traceability back to the source messages**. A user reading:

> "Alice proposed increasing marketing spend by 15%."

has no way to verify *when* Alice said that, *which message* contained it, or *what the exact wording was*. This creates three concrete problems:

1. **Trust** — Users can't distinguish accurate paraphrasing from hallucination without re-reading the entire conversation.
2. **Context loss** — A summary that says "the team agreed" doesn't tell you whether that agreement was enthusiastic consensus or a single thumbs-up emoji at 2am.
3. **Actionability** — Action items lose urgency and ownership when disconnected from the moment they were raised.

This problem is amplified for WhatsApp summaries (ADR-002/003) because WhatsApp conversations are informal, fast-moving, and lack Discord's structured threading — making it harder to find the original context after the fact.

---

## 2. Decision

Embed **message-level citations** into every structured element of a summary. Each key point, action item, decision, and participant attribution carries references to the specific message(s) that support it.

### 2.1 What a "Reference" Contains

A reference anchors a summary claim to one or more source messages:

```
┌─────────────────────────────────────────────────────────┐
│  Summary Claim                                          │
│  "Alice proposed increasing marketing spend by 15%"     │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Reference                                      │    │
│  │  message_id: "3EB0A8B2F7C7"                     │    │
│  │  sender: "Bob"                                   │    │
│  │  timestamp: 2026-02-10T14:32:00Z                │    │
│  │  snippet: "I think we need to increase the       │    │
│  │            marketing allocation by 15%"          │    │
│  │  position: 2 of 47                              │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

| Field | Type | Description |
|-------|------|-------------|
| `message_id` | `string` | Source-native message ID (WhatsApp hex ID, Discord snowflake) |
| `sender` | `string` | Display name of the message author |
| `timestamp` | `datetime` | When the message was sent |
| `snippet` | `string` | Relevant excerpt from the message (max 200 chars) |
| `position` | `int` | 1-based ordinal position in the conversation window |

`position` is the most important field for human readability — it lets a reader say "this came from message 2 of 47" and quickly locate it in a message list or export.

---

## 3. Data Model Changes

### 3.1 New: `MessageReference` Model

```python
# src/models/reference.py

from pydantic import BaseModel, Field
from datetime import datetime

class MessageReference(BaseModel):
    """A citation pointing to a specific source message."""
    message_id: str
    sender: str
    timestamp: datetime
    snippet: str = Field(max_length=200)
    position: int = Field(ge=1, description="1-based position in the conversation window")

class ReferencedClaim(BaseModel):
    """A summary claim with one or more supporting references."""
    text: str
    references: list[MessageReference] = Field(min_length=1)
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Model's self-assessed confidence that the claim is supported by the cited messages"
    )
```

### 3.2 Modified: Summary Output Model

Currently, SummaryBot-NG's summary output (in `src/models/summary.py`) contains flat string lists for key points, action items, etc. These need to become `ReferencedClaim` objects.

```python
# Changes to src/models/summary.py

class SummaryResult(BaseModel):
    # BEFORE (flat strings):
    # key_points: list[str]
    # action_items: list[str]
    # decisions: list[str]

    # AFTER (referenced claims):
    key_points: list[ReferencedClaim]
    action_items: list[ReferencedClaim]
    decisions: list[ReferencedClaim]
    topics: list[ReferencedClaim]

    # Participant summaries gain per-participant references
    participants: list[ParticipantSummary]

    # Conversation-level metadata (unchanged)
    message_count: int
    time_range_start: datetime
    time_range_end: datetime
    summary_type: str
    source_type: str

    # NEW: full reference index for the summary
    reference_index: list[MessageReference] = []

class ParticipantSummary(BaseModel):
    name: str
    message_count: int
    key_contributions: list[ReferencedClaim]  # was list[str]
    sentiment: str | None = None
```

### 3.3 Backward Compatibility

The API response changes shape. To avoid breaking existing consumers:

- Add a query parameter `?references=true|false` (default: `true` for JSON, `false` for markdown/plain)
- When `references=false`, flatten `ReferencedClaim` back to plain strings in the response serializer
- The `/discord/channels/{id}/summarize` endpoint defaults to `references=false` until consumers opt in
- The `/whatsapp/chats/{jid}/summarize` endpoint defaults to `references=true` (new endpoint, no legacy consumers)

---

## 4. Prompt Engineering

The core change: tell Claude to cite its sources. This requires two things in the prompt:

### 4.1 Message Numbering in Context

Every message sent to Claude in the conversation window gets a sequential position number:

```
--- CONVERSATION START ---
[1] Alice (2026-02-10 14:30): Has everyone reviewed the Q1 budget proposal?
[2] Bob (2026-02-10 14:32): Yes, I think we need to increase the marketing allocation by 15%
[3] Alice (2026-02-10 14:33): That's a big jump. Can you justify it?
[4] Bob (2026-02-10 14:35): Last quarter we underspent on marketing and missed our lead gen targets by 20%. The 15% increase brings us back to the level that worked in Q3.
[5] Carol (2026-02-10 14:40): I agree with Bob. We lost momentum in Q4.
[6] Alice (2026-02-10 14:42): OK, let's go with it. Bob, can you update the spreadsheet?
--- CONVERSATION END ---
```

This is a change to `src/summarization/prompt_builder.py` — the message formatting function needs to prepend `[N]` to each message.

### 4.2 Citation Instructions in System Prompt

Add citation instructions to the system prompt (both Discord and WhatsApp variants):

```
When writing the summary, you MUST cite the specific messages that support
each claim. Use the message position numbers shown in square brackets.

For each key point, action item, decision, or participant contribution:
- Include one or more citation numbers in the format [N] or [N,M,P]
- Choose the most specific message(s) — prefer direct quotes over inferences
- If a claim is synthesized from a general theme across many messages,
  cite 2-3 representative messages and note it as "[N,M,...+K more]"

Example output format:
{
  "key_points": [
    {
      "text": "Bob proposed increasing marketing allocation by 15% to recover Q4 lead gen shortfall",
      "references": [2, 4],
      "confidence": 0.95
    },
    {
      "text": "The team reached consensus to proceed with the increase",
      "references": [5, 6],
      "confidence": 0.9
    }
  ],
  "action_items": [
    {
      "text": "Bob to update the Q1 budget spreadsheet with the 15% marketing increase",
      "references": [6],
      "confidence": 1.0
    }
  ],
  "decisions": [
    {
      "text": "Approved: 15% increase to marketing allocation for Q1",
      "references": [2, 5, 6],
      "confidence": 0.95
    }
  ]
}
```

### 4.3 Structured Output Schema

Use Claude's tool-use / structured output mode to enforce the citation schema. This guarantees that every claim carries references rather than relying on the model to follow formatting instructions in free text.

```python
# Citation-aware output schema passed to Claude
SUMMARY_WITH_REFERENCES_SCHEMA = {
    "type": "object",
    "properties": {
        "key_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "references": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                        "description": "Message position numbers that support this claim"
                    },
                    "confidence": {
                        "type": "number", "minimum": 0, "maximum": 1
                    }
                },
                "required": ["text", "references"]
            }
        },
        "action_items": { "...same shape..." },
        "decisions": { "...same shape..." },
        "topics": { "...same shape..." },
        "participants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "message_count": {"type": "integer"},
                    "key_contributions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "references": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 1
                                }
                            },
                            "required": ["text", "references"]
                        }
                    }
                },
                "required": ["name", "key_contributions"]
            }
        }
    },
    "required": ["key_points", "action_items", "decisions", "participants"]
}
```

---

## 5. Response Processing — Reference Resolution

Claude returns position numbers (integers). The response parser must **resolve** these back to full `MessageReference` objects using the position-to-message mapping built during prompt construction.

### 5.1 Position Index

Built during prompt formatting:

```python
# src/summarization/prompt_builder.py

class PositionIndex:
    """Maps [N] position numbers to source message metadata."""

    def __init__(self, messages: list[ProcessedMessage]):
        self._index: dict[int, ProcessedMessage] = {}
        for i, msg in enumerate(messages, start=1):
            self._index[i] = msg

    def resolve(self, position: int) -> MessageReference:
        msg = self._index[position]
        return MessageReference(
            message_id=msg.id,
            sender=msg.author_name,
            timestamp=msg.timestamp,
            snippet=msg.content[:200],
            position=position,
        )

    def resolve_many(self, positions: list[int]) -> list[MessageReference]:
        return [self.resolve(p) for p in positions if p in self._index]
```

### 5.2 Modified Response Parser

```python
# Changes to src/summarization/response_parser.py

def parse_referenced_summary(
    raw_response: dict,
    position_index: PositionIndex,
) -> SummaryResult:
    """Parse Claude's structured response and resolve position references."""

    key_points = []
    for kp in raw_response.get("key_points", []):
        refs = position_index.resolve_many(kp["references"])
        key_points.append(ReferencedClaim(
            text=kp["text"],
            references=refs,
            confidence=kp.get("confidence", 1.0),
        ))

    # Same pattern for action_items, decisions, topics, participants...

    return SummaryResult(
        key_points=key_points,
        action_items=action_items,
        decisions=decisions,
        # ... build full reference index from all resolved refs
        reference_index=build_deduped_index(key_points, action_items, decisions),
    )
```

---

## 6. Output Rendering

Different output formats render references differently:

### 6.1 JSON (API default)

Full structured output with complete `MessageReference` objects. Consumers can build their own UI.

### 6.2 Markdown

Inline superscript-style citations with a footnote section:

```markdown
## Key Points

- Bob proposed increasing marketing allocation by 15% to recover Q4 lead gen shortfall [2][4]
- The team reached consensus to proceed with the increase [5][6]

## Action Items

- [ ] **Bob** to update the Q1 budget spreadsheet with the 15% marketing increase [6]

## Decisions

- **Approved:** 15% increase to marketing allocation for Q1 [2][5][6]

---

### Sources

| # | Who | When | Said |
|---|-----|------|------|
| [2] | Bob | 14:32 | "I think we need to increase the marketing allocation by 15%" |
| [4] | Bob | 14:35 | "Last quarter we underspent on marketing and missed our lead gen targets by 20%..." |
| [5] | Carol | 14:40 | "I agree with Bob. We lost momentum in Q4." |
| [6] | Alice | 14:42 | "OK, let's go with it. Bob, can you update the spreadsheet?" |
```

### 6.3 HTML

Clickable reference links. If the source platform has deep-linking (Discord message URLs), the reference links directly to the original message. For WhatsApp (no deep-linking), the link scrolls to the message in SummaryBot-NG's message viewer.

### 6.4 Plain Text

Parenthetical references: `(Bob, 14:32)` after each claim.

---

## 7. File-by-File Change Map

| # | File | Action | Risk | Description |
|---|------|--------|------|-------------|
| 1 | `src/models/reference.py` | **N** | Low | `MessageReference`, `ReferencedClaim` models |
| 2 | `src/models/summary.py` | **M** | Medium | Change flat `list[str]` fields to `list[ReferencedClaim]` |
| 3 | `src/summarization/prompt_builder.py` | **M** | Medium | Add `[N]` message numbering; build `PositionIndex`; add citation instructions to system prompts |
| 4 | `src/summarization/response_parser.py` | **M** | Medium | Resolve position numbers to `MessageReference` objects |
| 5 | `src/summarization/engine.py` | **M** | Low | Thread `PositionIndex` from prompt builder to response parser |
| 6 | `src/summarization/output_formatter.py` | **M** | Low | Render references in markdown/HTML/plain formats |
| 7 | `src/feeds/whatsapp_routes.py` | **M** | Low | Add `?references=` query param |
| 8 | `src/feeds/discord_routes.py` (or equivalent) | **M** | Low | Add `?references=` query param, default `false` |
| 9 | `tests/test_reference_resolution.py` | **N** | — | Unit tests for `PositionIndex` and reference resolution |
| 10 | `tests/test_referenced_summary_parsing.py` | **N** | — | Tests for parsing Claude output with citations |
| 11 | `tests/test_output_formatting_references.py` | **N** | — | Tests for markdown/HTML/plain reference rendering |

**Totals:** 8 files modified, 4 files created, 0 files deleted.

---

## 8. Edge Cases and Mitigations

| Edge Case | Mitigation |
|-----------|------------|
| Claude cites a position number that doesn't exist | `PositionIndex.resolve()` silently drops invalid positions; log a warning |
| Claude returns no references for a claim | Fail validation — the structured output schema requires `minItems: 1`. If the model still omits them, fall back to unreferenced claim with `confidence: 0.0` |
| Very long conversations (>500 messages) | Position numbers still work; truncation strategies (already in SummaryBot-NG) reduce the window but positions remain valid within the window |
| A single message supports many claims | Fine — the same `MessageReference` appears in multiple claims. The `reference_index` deduplicates |
| Forwarded messages | Cited like any other message. The snippet includes `[forwarded]` prefix for context |
| Deleted/edited messages | Reference reflects the message as it was at ingest time. Add `is_edited: bool` to `MessageReference` if needed later |
| Multi-language conversations | Citations are language-agnostic — they point to positions, not text patterns |

---

## 9. Token Cost Impact

Adding `[N]` prefixes and citation instructions increases prompt size:

| Component | Token Overhead |
|-----------|---------------|
| `[N] ` prefix per message (avg 3 tokens) | ~3 * message_count |
| Citation instructions in system prompt | ~250 tokens (fixed) |
| Structured output schema | ~200 tokens (fixed) |
| **Total for 100-message conversation** | ~750 extra tokens (~1.5% of a typical 50K context) |
| **Total for 500-message conversation** | ~1,950 extra tokens (~1.3% of a typical 150K context) |

The output side is slightly larger because Claude returns reference arrays, but structured output is generally more token-efficient than free-text anyway.

---

## 10. Implementation Phases

### Phase 1 — Core Reference Model (1-2 days)
- [ ] Create `src/models/reference.py` with `MessageReference` and `ReferencedClaim`
- [ ] Build `PositionIndex` in prompt builder
- [ ] Add `[N]` prefixes to message formatting

### Phase 2 — Prompt + Structured Output (2-3 days)
- [ ] Add citation instructions to system prompts (both Discord and WhatsApp variants)
- [ ] Define `SUMMARY_WITH_REFERENCES_SCHEMA` for Claude structured output
- [ ] Update `engine.py` to pass schema and thread `PositionIndex`

### Phase 3 — Response Parsing (1-2 days)
- [ ] Update `response_parser.py` to resolve position references
- [ ] Update `SummaryResult` model to use `ReferencedClaim`
- [ ] Add `?references=` query parameter to API endpoints

### Phase 4 — Output Rendering (1-2 days)
- [ ] Markdown rendering with `[N]` inline citations + sources table
- [ ] HTML rendering with anchor links
- [ ] Plain text rendering with parenthetical citations

### Phase 5 — Tests + Polish (1-2 days)
- [ ] Unit tests for `PositionIndex`
- [ ] Tests for structured output parsing with citations
- [ ] Tests for each output format
- [ ] Backward-compatibility tests (existing Discord consumers get flat strings when `references=false`)

---

## 11. Future Extensions

| Extension | Description |
|-----------|-------------|
| **Confidence thresholding** | Filter out claims below a confidence threshold in the output |
| **Deep-link URLs** | For Discord, generate `https://discord.com/channels/...` URLs in references. For WhatsApp, link to SummaryBot-NG's message viewer |
| **Reference clustering** | Group references by thread/topic to show conversation flow |
| **Diff-aware summaries** | When re-summarizing an updated conversation, highlight which claims are new vs. unchanged |
| **Interactive verification** | UI where clicking a claim highlights the referenced messages in the conversation view |
| **Cross-chat references** | For cross-chat summaries (ADR-002 §11.2), references include the chat name alongside position |

---

## 12. Consequences

### Positive
- **Summaries become verifiable** — every claim traces to specific messages
- **Reduces hallucination risk** — forcing citations makes the model more grounded
- **Enables interactive UIs** — click a claim to see the source
- **Source-agnostic** — works identically for Discord, WhatsApp, and future sources
- **Minimal token overhead** — <2% increase in prompt size

### Negative
- **Structured output required** — free-text summary mode can't carry references natively (mitigated by `?references=false` fallback)
- **Prompt complexity** — citation instructions add cognitive load to the prompt; may slightly reduce summary quality for very short conversations where citations are overkill
- **Schema coupling** — the structured output schema must stay in sync with the `SummaryResult` model

### Trade-offs
- Position-based references (simple, compact) vs. message-ID references in prompt (more robust but more tokens) — we chose position-based in the prompt, resolved to full references in post-processing
- Per-claim references vs. a single "sources" section — we chose per-claim for tighter grounding, with a deduped index for overview

---

## 13. References

- [ADR-002: WhatsApp Data Source Integration](./002-whatsapp-datasource-integration-summarybotng.md) — Ingest pipeline that provides the source messages
- [ADR-003: SummaryBot-NG Modifications](./003-summarybotng-modifications-for-whatsapp.md) — File-level changes to SummaryBot-NG (this ADR extends prompt_builder and response_parser further)
- [Anthropic: Tool Use / Structured Output](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) — Claude structured output for enforcing citation schema
- [Google NotebookLM Citations](https://notebooklm.google/) — Prior art: LLM-generated summaries with source citations
- [Perplexity AI](https://www.perplexity.ai/) — Prior art: search answers with inline source references
- [RAG Citation Patterns](https://arxiv.org/abs/2305.14627) — Academic work on LLM attribution and citation
