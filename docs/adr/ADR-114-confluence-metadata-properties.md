# ADR-114: Confluence Metadata and Page Properties

## Status
Accepted

## Context
When publishing summaries to Confluence, we currently create pages with basic content and labels. Users need better ways to:
- Query summaries via CQL (Confluence Query Language)
- Create Page Properties Reports for dashboards
- Filter by time period (month, week)

## Decision

### 1. Content Properties (Queryable via CQL)

Store structured metadata via `PUT /wiki/rest/api/content/{id}/property/{key}`:

```json
// summarybot.period
{
  "start": "2026-04-26T23:59:00Z",
  "end": "2026-05-03T23:59:00Z"
}

// summarybot.channel
{
  "name": "General Chat",
  "id": "general-chat-fb84d9"
}

// summarybot.stats
{
  "messages": 756,
  "participants": 25
}
```

These enable CQL queries like:
```
content.property[summarybot.period].start >= "2026-04-01"
```

### 2. Enhanced Labels

In addition to existing labels (`summarybot`, `scope-channel`, `channel-*`), add:

| Label | Example | Purpose |
|-------|---------|---------|
| `period-YYYY-MM` | `period-2026-04` | Monthly filtering |
| `period-YYYY-wWW` | `period-2026-w17` | ISO week filtering |

### 3. Page Properties Macro

Add a Page Properties macro at the top of each page containing a structured table:

| Key | Value |
|-----|-------|
| Channel | General Chat |
| Period Start | 2026-04-26 |
| Period End | 2026-05-03 |
| Messages | 756 |
| Participants | 25 |

This enables Page Properties Report macros on parent pages for dashboard views.

## ADF Structure for Page Properties

```json
{
  "type": "extension",
  "attrs": {
    "extensionType": "com.atlassian.confluence.macro.core",
    "extensionKey": "details",
    "parameters": {
      "macroParams": {}
    }
  },
  "content": [
    {
      "type": "table",
      "content": [
        // Table rows with Key/Value columns
      ]
    }
  ]
}
```

## Implementation

1. Modify `ConfluencePublisher._format_adf_content()` to include Page Properties macro
2. Add `_set_content_properties()` method to set structured properties after page creation
3. Enhance `_generate_labels()` to include period labels
4. Call property setter after successful page create/update

## Consequences

### Positive
- Enables CQL-based queries for programmatic access
- Supports Page Properties Report for visual dashboards
- Period labels enable easy Confluence search filtering
- Structured metadata survives page content edits

### Negative
- Additional API calls per publish (3 property sets)
- Slightly more complex ADF structure

## References
- [Confluence Content Properties API](https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content-properties/)
- [Page Properties Macro](https://confluence.atlassian.com/doc/page-properties-macro-184550024.html)
- [CQL Field Reference](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/)
