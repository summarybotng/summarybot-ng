#!/usr/bin/env python3
"""
Demo: RuVector Single Page Migration

This demonstrates what migrating a wiki page to RuVector looks like.
Run against your actual database by setting DATABASE_URL.

For the actual page at:
https://summarybot.app/guilds/1283874310720716890/wiki/topics/agentic-flow.md

You would access the new comparison endpoint:
GET /api/v1/ruvector/guilds/1283874310720716890/compare/topic/agentic-flow
"""

import json
from datetime import datetime

# Sample data representing what might be in topics/agentic-flow.md
SAMPLE_PAGE = {
    "path": "topics/agentic-flow.md",
    "title": "Agentic Flow",
    "content": """# Agentic Flow

*Topic created from summary analysis*

## Overview

This topic was identified from recent discussions. [source:summary-abc123]

## Key Points

- Agentic flow provides multi-agent orchestration for complex tasks [source:summary-abc123]
- Supports hierarchical, mesh, and adaptive topologies [source:summary-def456]
- SONA learning improves search relevance over time [source:summary-ghi789]
- Coherence gate prevents hallucination accumulation [source:summary-ghi789]

## Update from summary-def456

Key Points:
- Claude-flow v3 introduces 60+ specialized agent types [source:summary-def456]
- AgentDB provides unified memory with HNSW vector search [source:summary-def456]

## Related Topics

- [[topics/claude-flow.md|Claude Flow]]
- [[topics/multi-agent.md|Multi-Agent Systems]]
""",
    "synthesis": """Agentic Flow is a multi-agent orchestration framework that coordinates specialized AI agents to complete complex tasks. It supports three main topologies:

1. **Hierarchical**: Queen-led coordination with specialized workers
2. **Mesh**: Peer-to-peer communication for fault tolerance
3. **Adaptive**: Dynamic topology switching based on workload

Key components include AgentDB for persistent memory, SONA learning for relevance optimization, and the Coherence Gate for hallucination prevention.

The system uses HNSW vector search for semantic retrieval and supports 60+ specialized agent types including coders, reviewers, testers, and domain experts.""",
    "source_refs": ["summary-abc123", "summary-def456", "summary-ghi789"],
}

SAMPLE_SOURCES = [
    {
        "id": "summary-abc123",
        "title": "Discord: #development - 2024-01-15",
        "content": """Today's discussion focused on the agentic flow architecture. The team decided to implement a hierarchical topology with a queen agent coordinating worker agents.

Key decisions:
- Use Claude as the primary LLM for agent reasoning
- Implement SONA (Self-Optimizing Neural Attention) for learning from user interactions
- Add coherence gate to validate new content against existing knowledge

Action items:
- @alice: Create ADR for agentic flow architecture
- @bob: Prototype the queen-worker coordination""",
        "metadata": {
            "channel_name": "development",
            "timestamp": "2024-01-15T10:30:00Z",
            "key_points": [
                "Hierarchical topology with queen agent",
                "SONA for learning from interactions",
                "Coherence gate for validation"
            ],
            "action_items": [
                "Create ADR for agentic flow",
                "Prototype queen-worker coordination"
            ]
        }
    },
    {
        "id": "summary-def456",
        "title": "Discord: #architecture - 2024-01-20",
        "content": """Architecture review session for claude-flow v3. Major changes include:

- 60+ specialized agent types now available
- AgentDB replaces fragmented memory systems
- HNSW vector search for semantic retrieval
- Support for mesh and adaptive topologies in addition to hierarchical

The team agreed that mesh topology provides better fault tolerance for distributed workloads.""",
        "metadata": {
            "channel_name": "architecture",
            "timestamp": "2024-01-20T14:00:00Z",
            "key_points": [
                "60+ specialized agent types",
                "AgentDB unified memory",
                "HNSW vector search",
                "Mesh topology for fault tolerance"
            ]
        }
    },
    {
        "id": "summary-ghi789",
        "title": "Discord: #development - 2024-01-25",
        "content": """Implemented SONA learning and coherence gate. Key points:

SONA tracks three signal tiers:
1. Immediate: click-through rates, dwell time
2. Session: query refinement patterns
3. Long-term: content evolution trends

The coherence gate checks for:
- Contradictions with existing facts
- Duplicate content
- Semantic drift from topic clusters

Testing showed 15% improvement in search relevance after one week of learning.""",
        "metadata": {
            "channel_name": "development",
            "timestamp": "2024-01-25T16:00:00Z",
            "key_points": [
                "SONA tracks 3 signal tiers",
                "Coherence gate prevents contradictions",
                "15% search relevance improvement"
            ]
        }
    }
]


def extract_knowledge_units(source: dict) -> list:
    """Simulate knowledge unit extraction from a source."""
    units = []
    content = source["content"]
    metadata = source["metadata"]

    # Extract claims from key points
    for i, point in enumerate(metadata.get("key_points", [])):
        units.append({
            "id": f"{source['id']}-claim-{i}",
            "unit_type": "claim",
            "content": point,
            "source_id": source["id"],
            "source_channel": metadata.get("channel_name"),
            "source_date": metadata.get("timestamp"),
        })

    # Extract action items
    for i, action in enumerate(metadata.get("action_items", [])):
        units.append({
            "id": f"{source['id']}-action-{i}",
            "unit_type": "action_item",
            "content": action,
            "source_id": source["id"],
            "source_channel": metadata.get("channel_name"),
            "source_date": metadata.get("timestamp"),
        })

    # Look for decisions
    if "decided" in content.lower() or "agreed" in content.lower():
        # Find the decision sentence
        for sentence in content.split("."):
            if "decided" in sentence.lower() or "agreed" in sentence.lower():
                units.append({
                    "id": f"{source['id']}-decision-0",
                    "unit_type": "decision",
                    "content": sentence.strip(),
                    "source_id": source["id"],
                    "source_channel": metadata.get("channel_name"),
                    "source_date": metadata.get("timestamp"),
                })
                break

    return units


def render_ruvector_view(topic: str, units: list) -> str:
    """Simulate RuVector view rendering from knowledge units."""

    # Group by type
    claims = [u for u in units if u["unit_type"] == "claim"]
    decisions = [u for u in units if u["unit_type"] == "decision"]
    actions = [u for u in units if u["unit_type"] == "action_item"]

    # Group claims by channel for narrative flow
    by_channel = {}
    for claim in claims:
        ch = claim.get("source_channel", "general")
        if ch not in by_channel:
            by_channel[ch] = []
        by_channel[ch].append(claim)

    # Build view
    lines = [
        f"# {topic.title()}",
        "",
        f"*Generated from {len(units)} knowledge units across {len(set(u['source_id'] for u in units))} sources*",
        "",
    ]

    # Key facts section
    if claims:
        lines.append("## Key Facts")
        lines.append("")
        for claim in claims[:8]:
            lines.append(f"- {claim['content']}")
        lines.append("")

    # Decisions section
    if decisions:
        lines.append("## Decisions")
        lines.append("")
        for decision in decisions:
            date = decision.get("source_date", "")[:10] if decision.get("source_date") else ""
            lines.append(f"- **{date}**: {decision['content']}")
        lines.append("")

    # Action items section
    if actions:
        lines.append("## Action Items")
        lines.append("")
        for action in actions:
            lines.append(f"- [ ] {action['content']}")
        lines.append("")

    # Channel-based narrative
    lines.append("## Discussion Timeline")
    lines.append("")
    for channel, channel_claims in sorted(by_channel.items()):
        dates = sorted(set(c.get("source_date", "")[:10] for c in channel_claims if c.get("source_date")))
        if dates:
            lines.append(f"### #{channel} ({dates[0]} - {dates[-1]})")
        else:
            lines.append(f"### #{channel}")
        lines.append("")
        for claim in channel_claims:
            lines.append(f"- {claim['content']}")
        lines.append("")

    return "\n".join(lines)


def main():
    print("=" * 70)
    print("RuVector Migration Demo: topics/agentic-flow.md")
    print("=" * 70)

    # Show existing page
    print("\n📄 EXISTING WIKI PAGE")
    print("-" * 70)
    print(f"Path: {SAMPLE_PAGE['path']}")
    print(f"Title: {SAMPLE_PAGE['title']}")
    print(f"Sources: {len(SAMPLE_PAGE['source_refs'])}")
    print(f"\nContent ({len(SAMPLE_PAGE['content'])} chars):")
    print(SAMPLE_PAGE['content'][:800])
    print("...")

    print(f"\nSynthesis ({len(SAMPLE_PAGE['synthesis'])} chars):")
    print(SAMPLE_PAGE['synthesis'])

    # Extract knowledge units
    print("\n" + "=" * 70)
    print("🔄 EXTRACTING KNOWLEDGE UNITS")
    print("-" * 70)

    all_units = []
    for source in SAMPLE_SOURCES:
        units = extract_knowledge_units(source)
        all_units.extend(units)
        print(f"\n{source['id']}:")
        print(f"  - {len([u for u in units if u['unit_type'] == 'claim'])} claims")
        print(f"  - {len([u for u in units if u['unit_type'] == 'decision'])} decisions")
        print(f"  - {len([u for u in units if u['unit_type'] == 'action_item'])} action items")

    print(f"\nTotal: {len(all_units)} knowledge units")

    # Show units
    print("\n📦 KNOWLEDGE UNITS")
    print("-" * 70)
    for i, unit in enumerate(all_units):
        print(f"\n[{i+1}] {unit['unit_type'].upper()}")
        print(f"    {unit['content'][:80]}{'...' if len(unit['content']) > 80 else ''}")
        print(f"    Source: {unit['source_channel']} @ {unit['source_date'][:10] if unit['source_date'] else 'N/A'}")

    # Generate RuVector view
    print("\n" + "=" * 70)
    print("✨ RUVECTOR GENERATED VIEW")
    print("-" * 70)

    ruvector_view = render_ruvector_view("Agentic Flow", all_units)
    print(ruvector_view)

    # Comparison summary
    print("\n" + "=" * 70)
    print("📊 COMPARISON SUMMARY")
    print("-" * 70)
    print(f"""
Metric                    Existing Wiki    RuVector
-----------------------   -------------    --------
Content length            {len(SAMPLE_PAGE['content']):>5} chars      {len(ruvector_view):>5} chars
Synthesis length          {len(SAMPLE_PAGE['synthesis']):>5} chars      N/A (dynamic)
Source references         {len(SAMPLE_PAGE['source_refs']):>5}            {len(set(u['source_id'] for u in all_units)):>5}
Knowledge units           N/A              {len(all_units):>5}
  - Claims                N/A              {len([u for u in all_units if u['unit_type'] == 'claim']):>5}
  - Decisions             N/A              {len([u for u in all_units if u['unit_type'] == 'decision']):>5}
  - Action Items          N/A              {len([u for u in all_units if u['unit_type'] == 'action_item']):>5}

Key Differences:
1. RuVector structures content by unit type (claims, decisions, actions)
2. RuVector provides timeline-based narrative by channel
3. RuVector units are searchable via semantic similarity
4. RuVector learns from user interactions (SONA)
5. RuVector validates new content (Coherence Gate)
""")

    print("\n" + "=" * 70)
    print("🔗 API ENDPOINTS FOR THIS PAGE")
    print("-" * 70)
    print("""
# Existing wiki synthesis (unchanged):
GET /api/v1/guilds/1283874310720716890/wiki/pages/topics/agentic-flow.md

# RuVector semantic search:
GET /api/v1/ruvector/guilds/1283874310720716890/search?q=agentic+flow

# RuVector topic view:
GET /api/v1/ruvector/guilds/1283874310720716890/views/topic/agentic-flow

# Side-by-side comparison (NEW):
GET /api/v1/ruvector/guilds/1283874310720716890/compare/topic/agentic-flow

# Backfill existing content to RuVector:
POST /api/v1/ruvector/guilds/1283874310720716890/backfill
""")


if __name__ == "__main__":
    main()
