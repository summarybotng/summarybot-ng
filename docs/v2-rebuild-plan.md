# SummaryBot V2: Clean Room Rebuild Plan

**Date**: 2026-06-03
**Approach**: Clean room rebuild (no strangler fig needed)
**Rationale**: No production dependency, source data on underlying systems

---

## Prerequisites

- [ ] PRD complete (`docs/PRD-rewrite.md`)
- [ ] Endpoint inventory (`docs/PRD-rewrite-appendix-endpoints.md`)
- [ ] Technical debt documented (`docs/technical-debt.md`)
- [ ] Future requirements captured (PRD Section 13)

---

## Architecture Principles

### From Day 1

1. **No file > 300 lines** (CI enforced)
2. **No function > 30 lines**
3. **80% test coverage minimum** (CI gate)
4. **Contracts before implementation**
5. **Domain has zero external dependencies**
6. **All state in database** (no in-memory dicts)

### Directory Structure

```
summarybot-v2/
├── pyproject.toml
├── .github/
│   └── workflows/
│       └── ci.yml           # Coverage gates, linting, type checks
├── src/
│   ├── api/                 # HTTP layer (thin)
│   │   ├── __init__.py
│   │   ├── app.py           # FastAPI app factory
│   │   ├── deps.py          # Dependency injection
│   │   └── routes/
│   │       ├── auth.py      # < 150 lines
│   │       ├── workspaces.py
│   │       ├── summaries.py
│   │       ├── schedules.py
│   │       └── ...
│   ├── domain/              # Pure business logic (NO I/O)
│   │   ├── __init__.py
│   │   ├── models/
│   │   │   ├── workspace.py
│   │   │   ├── summary.py
│   │   │   ├── schedule.py
│   │   │   └── user.py
│   │   ├── events.py        # Domain events
│   │   ├── errors.py        # Domain exceptions
│   │   └── ports.py         # Repository interfaces
│   ├── services/            # Application layer (orchestration)
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── summary_service.py
│   │   ├── schedule_service.py
│   │   └── delivery_service.py
│   ├── adapters/            # Infrastructure implementations
│   │   ├── __init__.py
│   │   ├── repositories/
│   │   │   ├── sqlite/
│   │   │   │   ├── summary_repo.py
│   │   │   │   ├── schedule_repo.py
│   │   │   │   └── ...
│   │   │   └── migrations/
│   │   ├── platforms/       # Discord, Slack, WhatsApp
│   │   │   ├── base.py      # Abstract adapter
│   │   │   ├── discord.py
│   │   │   ├── slack.py
│   │   │   └── whatsapp.py
│   │   ├── llm/
│   │   │   └── openrouter.py
│   │   └── delivery/
│   │       ├── discord.py
│   │       ├── email.py
│   │       ├── webhook.py
│   │       └── confluence.py
│   └── shared/              # Cross-cutting concerns
│       ├── config.py
│       ├── logging.py
│       └── time.py
├── tests/
│   ├── unit/
│   │   ├── domain/          # Fast, no I/O
│   │   └── services/
│   ├── integration/
│   │   ├── repositories/
│   │   └── adapters/
│   └── e2e/
│       └── api/
├── scripts/
│   ├── migrate.py           # DB migrations
│   └── import_v1_data.py    # One-time import from v1
└── docs/
    └── adr/                  # Fresh ADRs for v2 decisions
```

---

## Week 1: Foundation

### Day 1-2: Project Setup

```bash
# Initialize
mkdir summarybot-v2 && cd summarybot-v2
uv init
uv add fastapi uvicorn sqlalchemy aiosqlite pydantic
uv add --dev pytest pytest-asyncio pytest-cov ruff mypy

# Create structure
mkdir -p src/{api/routes,domain/models,services,adapters/{repositories/sqlite,platforms,delivery},shared}
mkdir -p tests/{unit/{domain,services},integration/{repositories,adapters},e2e/api}
```

### Day 2-3: CI Pipeline

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync

      - name: Lint
        run: uv run ruff check src/

      - name: Type check
        run: uv run mypy src/

      - name: Test with coverage
        run: |
          uv run pytest --cov=src --cov-fail-under=80 --cov-report=xml

      - name: Check file sizes
        run: |
          find src -name "*.py" -exec wc -l {} + | awk '$1 > 300 {print "ERROR: " $2 " has " $1 " lines"; exit 1}'
```

### Day 3: Domain Contracts

```python
# src/domain/ports.py
from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import datetime

from .models.summary import Summary, SummaryFilters
from .models.workspace import Workspace
from .models.schedule import Schedule

class SummaryRepository(ABC):
    @abstractmethod
    async def save(self, summary: Summary) -> None: ...

    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[Summary]: ...

    @abstractmethod
    async def list_by_workspace(
        self,
        workspace_id: str,
        filters: SummaryFilters,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Summary], int]: ...

    @abstractmethod
    async def delete(self, id: str) -> bool: ...


class WorkspaceRepository(ABC):
    @abstractmethod
    async def save(self, workspace: Workspace) -> None: ...

    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[Workspace]: ...

    @abstractmethod
    async def get_by_connection(
        self, platform: str, platform_id: str
    ) -> Optional[Workspace]: ...


class ScheduleRepository(ABC):
    @abstractmethod
    async def save(self, schedule: Schedule) -> None: ...

    @abstractmethod
    async def get_due(self, now: datetime) -> List[Schedule]: ...

    @abstractmethod
    async def update_last_run(self, id: str, ran_at: datetime) -> None: ...


class MessageFetcher(ABC):
    """Platform adapter for fetching messages."""

    @property
    @abstractmethod
    def platform(self) -> str: ...

    @abstractmethod
    async def fetch_messages(
        self,
        channel_id: str,
        since: datetime,
        until: datetime,
    ) -> List["NormalizedMessage"]: ...

    @abstractmethod
    async def list_channels(self) -> List["NormalizedChannel"]: ...


class SummaryGenerator(ABC):
    """LLM adapter for generating summaries."""

    @abstractmethod
    async def generate(
        self,
        messages: List["NormalizedMessage"],
        options: "GenerationOptions",
    ) -> "GenerationResult": ...
```

---

## Week 2-3: Core Domain + Auth

### Domain Models (Pure, No Dependencies)

```python
# src/domain/models/workspace.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum

class Platform(Enum):
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"

@dataclass
class PlatformConnection:
    id: str
    platform: Platform
    platform_id: str  # guild_id, team_id, etc.
    platform_name: str
    connected_at: datetime

@dataclass
class Workspace:
    id: str
    name: str
    owner_id: str
    connections: List[PlatformConnection] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def has_platform(self, platform: Platform) -> bool:
        return any(c.platform == platform for c in self.connections)

    def get_connection(self, platform: Platform) -> Optional[PlatformConnection]:
        return next(
            (c for c in self.connections if c.platform == platform),
            None
        )
```

```python
# src/domain/models/summary.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

@dataclass
class ActionItem:
    content: str
    assignee: Optional[str] = None
    deadline: Optional[datetime] = None
    priority: str = "medium"
    completed: bool = False

@dataclass
class Summary:
    id: str
    workspace_id: str
    channel_ids: List[str]
    content: str
    key_points: List[str]
    action_items: List[ActionItem]
    message_count: int
    start_time: datetime
    end_time: datetime
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Computed properties (pure logic)
    @property
    def has_pending_actions(self) -> bool:
        return any(not item.completed for item in self.action_items)

    @property
    def duration_hours(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 3600
```

### Authentication Service

```python
# src/services/auth_service.py
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from ..domain.models.user import User
from ..domain.models.workspace import Workspace
from ..domain.ports import UserRepository, WorkspaceRepository

class AuthProvider(Enum):
    DISCORD = "discord"
    SLACK = "slack"
    GOOGLE = "google"
    EMAIL = "email"

@dataclass
class AuthResult:
    user: User
    workspaces: list[Workspace]
    access_token: str
    refresh_token: str

class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        workspace_repo: WorkspaceRepository,
        token_service: "TokenService",
    ):
        self._users = user_repo
        self._workspaces = workspace_repo
        self._tokens = token_service

    async def authenticate(
        self,
        provider: AuthProvider,
        credentials: dict
    ) -> AuthResult:
        """Authenticate via any provider, return unified user."""
        # Get platform-specific user info
        platform_user = await self._verify_with_provider(provider, credentials)

        # Find or create unified user
        user = await self._users.get_by_identity(
            provider.value, platform_user.id
        )
        if not user:
            user = User.create(
                name=platform_user.name,
                email=platform_user.email,
            )
            user.add_identity(provider.value, platform_user.id)
            await self._users.save(user)

        # Get accessible workspaces
        workspaces = await self._workspaces.get_by_user(user.id)

        # Generate tokens
        access_token = self._tokens.create_access_token(user, workspaces)
        refresh_token = self._tokens.create_refresh_token(user)

        return AuthResult(
            user=user,
            workspaces=workspaces,
            access_token=access_token,
            refresh_token=refresh_token,
        )
```

---

## Week 4-5: Summary Generation

### Summary Service (Orchestration)

```python
# src/services/summary_service.py
from dataclasses import dataclass
from datetime import datetime
from typing import List

from ..domain.models.summary import Summary
from ..domain.models.workspace import Workspace
from ..domain.ports import (
    SummaryRepository,
    MessageFetcher,
    SummaryGenerator,
)
from ..domain.events import SummaryGenerated

@dataclass
class GenerateRequest:
    workspace_id: str
    channel_ids: List[str]
    since: datetime
    until: datetime
    length: str = "detailed"
    perspective: str = "general"

class SummaryService:
    def __init__(
        self,
        summary_repo: SummaryRepository,
        fetcher: MessageFetcher,
        generator: SummaryGenerator,
        event_bus: "EventBus",
    ):
        self._summaries = summary_repo
        self._fetcher = fetcher
        self._generator = generator
        self._events = event_bus

    async def generate(self, request: GenerateRequest) -> Summary:
        # 1. Fetch messages from platform
        messages = []
        for channel_id in request.channel_ids:
            channel_msgs = await self._fetcher.fetch_messages(
                channel_id=channel_id,
                since=request.since,
                until=request.until,
            )
            messages.extend(channel_msgs)

        if len(messages) < 5:
            raise InsufficientMessagesError(
                f"Only {len(messages)} messages found, minimum 5 required"
            )

        # 2. Generate summary via LLM
        result = await self._generator.generate(
            messages=messages,
            options=GenerationOptions(
                length=request.length,
                perspective=request.perspective,
            ),
        )

        # 3. Create domain object
        summary = Summary(
            id=generate_id(),
            workspace_id=request.workspace_id,
            channel_ids=request.channel_ids,
            content=result.content,
            key_points=result.key_points,
            action_items=result.action_items,
            message_count=len(messages),
            start_time=request.since,
            end_time=request.until,
        )

        # 4. Persist
        await self._summaries.save(summary)

        # 5. Emit event
        await self._events.publish(SummaryGenerated(
            summary_id=summary.id,
            workspace_id=summary.workspace_id,
            channel_ids=summary.channel_ids,
            generated_at=summary.created_at,
            cost_usd=result.cost_usd,
        ))

        return summary
```

---

## Week 6: Scheduling

### Schedule Executor

```python
# src/services/schedule_service.py
import asyncio
from datetime import datetime
from typing import List

from ..domain.models.schedule import Schedule, ScheduleType
from ..domain.ports import ScheduleRepository
from .summary_service import SummaryService, GenerateRequest

class ScheduleService:
    def __init__(
        self,
        schedule_repo: ScheduleRepository,
        summary_service: SummaryService,
    ):
        self._schedules = schedule_repo
        self._summaries = summary_service
        self._running = False

    async def start(self):
        """Start the scheduler loop."""
        self._running = True
        while self._running:
            await self._tick()
            await asyncio.sleep(60)  # Check every minute

    async def _tick(self):
        """Process due schedules."""
        now = datetime.utcnow()
        due_schedules = await self._schedules.get_due(now)

        for schedule in due_schedules:
            try:
                await self._execute(schedule)
                await self._schedules.update_last_run(schedule.id, now)
                schedule.increment_run_count()
            except Exception as e:
                schedule.increment_failure_count()
                if schedule.failure_count >= schedule.max_failures:
                    schedule.disable()
                await self._schedules.save(schedule)

    async def _execute(self, schedule: Schedule):
        """Execute a single schedule."""
        # Calculate time range based on schedule type
        since, until = schedule.calculate_time_range()

        # Resolve channels (for category/workspace scope)
        channel_ids = await self._resolve_channels(schedule)

        # Generate summary
        summary = await self._summaries.generate(GenerateRequest(
            workspace_id=schedule.workspace_id,
            channel_ids=channel_ids,
            since=since,
            until=until,
            length=schedule.summary_options.length,
            perspective=schedule.summary_options.perspective,
        ))

        # Deliver to configured destinations
        await self._deliver(summary, schedule.destinations)
```

---

## Week 7: Delivery Adapters

```python
# src/adapters/delivery/base.py
from abc import ABC, abstractmethod
from ..domain.models.summary import Summary

class DeliveryAdapter(ABC):
    @property
    @abstractmethod
    def destination_type(self) -> str: ...

    @abstractmethod
    async def deliver(
        self,
        summary: Summary,
        target: str,
        options: dict
    ) -> "DeliveryResult": ...

# src/adapters/delivery/discord.py
class DiscordDeliveryAdapter(DeliveryAdapter):
    destination_type = "discord_channel"

    def __init__(self, bot_token: str):
        self._token = bot_token

    async def deliver(self, summary, target, options):
        # Format as embed
        embed = self._format_embed(summary, options)

        # Send via Discord API
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://discord.com/api/v10/channels/{target}/messages",
                headers={"Authorization": f"Bot {self._token}"},
                json={"embeds": [embed]},
            )

        return DeliveryResult(success=True, destination=target)
```

---

## Week 8: API Layer

```python
# src/api/routes/summaries.py
from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from datetime import datetime

from ..deps import get_summary_service, get_current_user
from ...services.summary_service import SummaryService, GenerateRequest
from ...domain.models.summary import Summary

router = APIRouter(prefix="/workspaces/{workspace_id}/summaries", tags=["summaries"])

@router.get("")
async def list_summaries(
    workspace_id: str,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    service: SummaryService = Depends(get_summary_service),
    user = Depends(get_current_user),
) -> dict:
    """List summaries for a workspace."""
    summaries, total = await service.list(workspace_id, limit=limit, offset=offset)
    return {
        "items": [s.to_dict() for s in summaries],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@router.post("/generate")
async def generate_summary(
    workspace_id: str,
    request: GenerateRequestDTO,
    service: SummaryService = Depends(get_summary_service),
    user = Depends(get_current_user),
) -> dict:
    """Generate a new summary."""
    summary = await service.generate(GenerateRequest(
        workspace_id=workspace_id,
        channel_ids=request.channel_ids,
        since=request.since,
        until=request.until,
        length=request.length,
        perspective=request.perspective,
    ))
    return summary.to_dict()
```

---

## Week 9: Migration Tooling

### Import from V1

```python
# scripts/import_v1_data.py
"""
One-time import of data from v1 to v2.

Run after v2 is deployed but before cutover.
"""
import asyncio
import sqlite3
from datetime import datetime

async def import_summaries(v1_db_path: str, v2_db_path: str):
    """Import stored summaries from v1."""
    v1_conn = sqlite3.connect(v1_db_path)
    v1_conn.row_factory = sqlite3.Row

    # Read v1 summaries
    rows = v1_conn.execute("""
        SELECT * FROM stored_summaries
        ORDER BY created_at
    """).fetchall()

    print(f"Found {len(rows)} summaries to import")

    # Transform and insert into v2
    for row in rows:
        # Map guild_id to workspace_id
        workspace_id = f"ws-{row['guild_id']}"

        # Transform to v2 schema
        v2_summary = {
            "id": row["id"],
            "workspace_id": workspace_id,
            "channel_ids": json.loads(row["source_channel_ids"]),
            "content": row["summary_result"]["summary_text"],
            # ... map all fields
        }

        await v2_repo.save(v2_summary)

    print(f"Imported {len(rows)} summaries")

async def import_schedules(v1_db_path: str, v2_db_path: str):
    """Import scheduled tasks from v1."""
    # Similar transformation logic
    pass

async def main():
    v1_path = "/path/to/summarybot.db"
    v2_path = "/path/to/summarybot-v2.db"

    await import_summaries(v1_path, v2_path)
    await import_schedules(v1_path, v2_path)
    # Import other entities...

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Week 10: Cutover

### Cutover Checklist

```markdown
## Pre-Cutover (Day -1)
- [ ] All tests passing (80%+ coverage)
- [ ] Manual QA complete
- [ ] Import scripts tested on copy of v1 data
- [ ] Rollback plan documented
- [ ] Team notified

## Cutover Day
- [ ] Stop v1 scheduler
- [ ] Run final import from v1 database
- [ ] Verify import counts match
- [ ] Update DNS / load balancer to v2
- [ ] Smoke test core flows:
  - [ ] Login (Discord)
  - [ ] List summaries
  - [ ] Generate summary
  - [ ] View schedule
  - [ ] Create schedule
- [ ] Monitor error rates
- [ ] Announce cutover complete

## Post-Cutover (Day +1 to +7)
- [ ] Monitor for issues
- [ ] Archive v1 codebase
- [ ] Delete v1 database (after confirmation period)
- [ ] Update documentation
```

---

## Future Phases (Post-Cutover)

### Phase 2: Platform-Agnostic Auth (Week 11-12)
Implement FUT-001 to FUT-006 from PRD Section 13.1

### Phase 3: Multi-Tenancy (Week 13-14)
Implement FUT-010 to FUT-015 from PRD Section 13.3

### Phase 4: Advanced Features (Week 15+)
- AI Wiki Curator
- Knowledge Base Agents
- RuVector full integration

---

## Key Metrics to Track

| Metric | V1 Current | V2 Target |
|--------|------------|-----------|
| Largest file | 5,574 lines | < 300 lines |
| Test coverage | 36% | 80%+ |
| Avg response time | ? | < 200ms |
| In-memory state | 3 locations | 0 |
| Migration gaps | Yes | No |

---

*Plan generated 2026-06-03*
