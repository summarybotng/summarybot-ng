# ADR-054: Operational Agents for Instance Management

## Status
Accepted

## Context

summarybot-ng is a multi-platform messaging summarization service supporting Discord and Slack. As the system grows in complexity with:

- Multiple platform integrations (ADR-051)
- Scheduled task management across platforms
- Token lifecycle management (Slack OAuth)
- Cross-platform data normalization
- Audit logging and compliance requirements

Manual operational oversight becomes impractical. We need autonomous agents to ensure system health, data quality, and platform connectivity.

## Decision

Introduce three specialized operational agents that work together to maintain system health:

### 1. Instance Operator

**Purpose**: System upkeep and operational health

**Responsibilities**:
- Record completeness audits (missing fields, orphaned records)
- Platform connectivity monitoring (Discord bot, Slack tokens)
- Scheduled task hygiene (orphaned schedules, high failure counts)
- Database maintenance (size tracking, vacuuming needs)
- Security compliance checks (encrypted tokens, audit log completeness)

**Trigger Conditions**:
- Post-deployment verification
- Weekly automated health checks
- After platform integration changes
- When users report missing data
- Before/after database migrations

### 2. Data Steward

**Purpose**: Data quality and consistency

**Responsibilities**:
- Summary data validation (non-empty text, valid key_points)
- Reference integrity checks (valid archive_source_key, channel_ids)
- Temporal consistency (start_time < end_time, valid schedules)
- Platform data normalization (Discord/Slack schema parity)
- Data retention management (age distribution, archival candidates)

**Trigger Conditions**:
- Daily automated quality scans
- After bulk imports or migrations
- When data inconsistencies reported
- Before compliance reports
- After platform integration changes

### 3. Platform Monitor

**Purpose**: Multi-platform API health and connectivity

**Responsibilities**:
- Discord health (bot connection, guild accessibility, rate limits)
- Slack health (OAuth token validity, workspace status, tier-based rate limits)
- Platform fetcher performance (success rates, latency comparison)
- Cross-platform consistency (ProcessedMessage normalization)
- Alerting on degraded conditions

**Trigger Conditions**:
- Continuous monitoring (30s-15m intervals depending on check type)
- On platform fetcher errors
- When scheduled tasks fail
- After OAuth token refresh attempts

## Agent Coordination

```
┌─────────────────────────────────────────────────────────────┐
│                    Dashboard / Admin UI                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Instance Operator                         │
│  • System upkeep    • Record completeness   • Security      │
│  Triggers: Weekly, post-deploy, on-demand                   │
└─────────────────────────────────────────────────────────────┘
          │                                       │
          ▼                                       ▼
┌─────────────────────┐             ┌─────────────────────────┐
│    Data Steward     │◄───────────►│   Platform Monitor      │
│ • Data quality      │             │ • API connectivity      │
│ • Reference checks  │  (shares    │ • Rate limit tracking   │
│ • Normalization     │  platform   │ • Token lifecycle       │
│ Daily scan          │  health)    │ Continuous monitoring   │
└─────────────────────┘             └─────────────────────────┘
          │                                       │
          ▼                                       ▼
┌─────────────────────────────────────────────────────────────┐
│                        Data Layer                            │
│  stored_summaries | scheduled_tasks | slack_workspaces      │
└─────────────────────────────────────────────────────────────┘
```

## Output Formats

All agents produce YAML-formatted reports:

```yaml
# Instance Operator
health_report:
  timestamp: ISO-8601
  overall_status: healthy|degraded|critical
  record_completeness: {...}
  platform_health: {...}
  recommendations: [...]

# Data Steward
data_quality_report:
  timestamp: ISO-8601
  tables_audited: [...]
  integrity_checks: {...}
  normalization: {...}
  recommendations: [...]

# Platform Monitor
platform_health_report:
  timestamp: ISO-8601
  discord: {...}
  slack: {...}
  platform_fetchers: {...}
  alerts: [...]
```

## Alert Severity Levels

| Level | Condition | Response |
|-------|-----------|----------|
| Critical | Discord gateway offline, Slack token invalid | Immediate notification |
| High | >10% fetch failures, token expires <24h | Alert admin |
| Medium | Orphaned schedules, incomplete records | Daily report |
| Warning | Rate limit >80%, data quality drift | Weekly report |
| Info | New workspace added, migration complete | Log only |

## Implementation

Agents are defined as Claude Code v3 subagent templates:

```
.claude/agents/v3/
├── instance-operator.md
├── data-steward.md
└── platform-monitor.md
```

Invocation via Task tool:

```javascript
// Run health check
Task({
  prompt: "Run full instance health check",
  subagent_type: "instance-operator"
})

// Run data quality scan
Task({
  prompt: "Audit summary data quality for guild X",
  subagent_type: "data-steward"
})

// Check platform health
Task({
  prompt: "Check all platform connectivity and report issues",
  subagent_type: "platform-monitor"
})
```

## Integration with Existing Systems

| System | Integration |
|--------|-------------|
| QE Fleet | Complements qe-coverage-specialist, qe-security-scanner |
| Dashboard | Reports feed into audit log and metrics |
| Scheduler | Instance operator validates schedules before execution |
| Release Manager | Health check required before deployments |

## Consequences

### Positive

- Automated health monitoring reduces manual oversight
- Proactive detection of data quality issues
- Platform connectivity issues caught before user impact
- Consistent audit trail for compliance
- Clear separation of concerns between agents

### Negative

- Additional agent definitions to maintain
- Coordination overhead between agents
- Potential for alert fatigue if thresholds not tuned
- Resource usage for continuous monitoring

### Mitigations

- Start with conservative alerting thresholds
- Implement alert aggregation/deduplication
- Schedule heavy scans during off-peak hours
- Share platform health state between agents to reduce duplicate checks

## References

- [ADR-051: Platform Message Fetcher Abstraction](./ADR-051-platform-message-fetcher-abstraction.md)
- [ADR-045: Audit Logging System](./ADR-045-audit-logging-system.md)
- [ADR-043: Slack Workspace Integration](./ADR-043-slack-workspace-integration-feasibility.md)
- `.claude/agents/v3/instance-operator.md`
- `.claude/agents/v3/data-steward.md`
- `.claude/agents/v3/platform-monitor.md`
