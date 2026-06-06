# Architecture: System Overview

**SPARC Phase**: Architecture
**Module**: System-wide

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                   CLIENTS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Web App    │  │  Discord Bot │  │   Slack App  │  │   REST API   │    │
│  │   (React)    │  │  (Commands)  │  │  (Commands)  │  │   (Webhooks) │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
└─────────┼─────────────────┼─────────────────┼─────────────────┼────────────┘
          │                 │                 │                 │
          └────────────────┬┴─────────────────┴─────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────────┐
│                              API LAYER (FastAPI)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  /auth/*     │  │ /workspaces/*│  │ /summaries/* │  │ /schedules/* │    │
│  │  OAuth flows │  │  CRUD, perms │  │  Gen, list   │  │  CRUD, exec  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Middleware Pipeline                           │   │
│  │  [Auth] → [RateLimit] → [Logging] → [ErrorHandler] → [Metrics]      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                            SERVICE LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ AuthService  │  │SummaryService│  │ScheduleServ │  │DeliveryServ  │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                 │                 │                 │             │
│  ┌──────┴─────────────────┴─────────────────┴─────────────────┴──────┐     │
│  │                         Event Bus                                  │     │
│  │  [SummaryGenerated] [ScheduleExecuted] [WorkspaceConnected] ...   │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                            DOMAIN LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Workspace   │  │   Summary    │  │   Schedule   │  │     User     │    │
│  │   Entity     │  │   Entity     │  │   Entity     │  │   Entity     │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          Ports (Interfaces)                          │   │
│  │  SummaryRepo │ WorkspaceRepo │ ScheduleRepo │ MessageFetcher │ ...  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                           ADAPTER LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐ │
│  │    Repositories     │  │  Platform Adapters  │  │  Delivery Adapters  │ │
│  ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤ │
│  │ SqliteSummaryRepo   │  │ DiscordFetcher      │  │ DiscordDelivery     │ │
│  │ SqliteWorkspaceRepo │  │ SlackFetcher        │  │ EmailDelivery       │ │
│  │ SqliteScheduleRepo  │  │ WhatsAppFetcher     │  │ WebhookDelivery     │ │
│  └──────────┬──────────┘  └──────────┬──────────┘  │ ConfluenceDelivery  │ │
│             │                        │             └──────────┬──────────┘ │
│  ┌──────────▼──────────┐  ┌──────────▼──────────┐             │            │
│  │     SQLite DB       │  │   Platform APIs     │  ┌──────────▼──────────┐ │
│  │  (summarybot.db)    │  │ Discord/Slack/WA    │  │   External APIs     │ │
│  └─────────────────────┘  └─────────────────────┘  │ SMTP/Confluence/... │ │
│                                                     └─────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         LLM Adapter                                  │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐  │   │
│  │  │ OpenRouter  │  │  Anthropic  │  │    GlobalRateLimiter        │  │   │
│  │  │  Adapter    │  │   Direct    │  │  (TokenBucket + Circuit)    │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow: Generate Summary

```
┌──────┐    ┌─────────┐    ┌───────────────┐    ┌─────────────┐    ┌────────┐
│Client│───▶│API Route│───▶│SummaryService │───▶│RateLimiter  │───▶│LLM API │
└──────┘    └─────────┘    └───────────────┘    └─────────────┘    └────────┘
                                  │                                     │
                                  │  ┌─────────────────┐               │
                                  ├─▶│MessageFetcher   │               │
                                  │  │(Platform API)   │               │
                                  │  └─────────────────┘               │
                                  │                                     │
                                  │  ┌─────────────────┐               │
                                  │◀─│GenerationResult │◀──────────────┘
                                  │  └─────────────────┘
                                  │
                                  │  ┌─────────────────┐
                                  ├─▶│SummaryRepository│───▶ SQLite
                                  │  └─────────────────┘
                                  │
                                  │  ┌─────────────────┐
                                  └─▶│EventBus         │───▶ Handlers
                                     │(SummaryGenerated│
                                     └─────────────────┘
```

## Key Boundaries

### 1. Domain (Pure)
- **No I/O**: Domain models never touch network/database
- **No frameworks**: No FastAPI, SQLAlchemy in domain
- **Rich behavior**: Business logic lives in entities

### 2. Services (Orchestration)
- **Thin**: Coordinate domain + adapters
- **Transaction boundaries**: Services own transaction scope
- **Event emission**: Services publish domain events

### 3. Adapters (Infrastructure)
- **Implement ports**: Concrete implementations of domain interfaces
- **Handle I/O**: All network, database, filesystem
- **Replaceable**: Can swap SQLite for Postgres without touching domain

### 4. API (Presentation)
- **Thin**: Convert HTTP to service calls
- **Validation**: Input validation at edge
- **Auth**: Middleware handles authentication

## Dependency Rule

```
API → Services → Domain ← Adapters
      ↓           ↑
      └───────────┘
      (depend on domain interfaces)
```

- **Domain** has zero external dependencies
- **Services** depend on domain ports (interfaces)
- **Adapters** implement domain ports
- **API** depends on services

---

*Next: `02-api-contracts.md`*
