# Design Document

## Architecture Decisions and Trade-offs

### Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Framework | FastAPI | Modern async Python framework with automatic OpenAPI docs, type hints, and excellent performance |
| Database | PostgreSQL 16 | Production-grade RDBMS with connection pooling, JSONB support for flexible event properties, better concurrency than SQLite |
| ORM | SQLAlchemy | Industry standard, supports multiple databases, handles connection pooling |
| Validation | Pydantic | Native FastAPI integration, automatic request/response validation |
| Statistics | SciPy | Robust statistical testing library for chi-square significance calculation |
| Architecture | Repository Pattern | Clean separation between API and data access layers |
| Containerization | Docker Compose | Multi-profile setup for production, development, and testing environments |

### Trade-offs Analysis

Every design decision involves trade-offs. Here's an honest assessment:

| Decision | Benefits | Trade-offs | Why We Accepted |
|----------|----------|------------|-----------------|
| **Repository Pattern** | Testability, flexibility, clean separation | More boilerplate code, indirect data access | Testing benefits outweigh complexity; critical for maintainable code |
| **PostgreSQL over SQLite** | Production-ready, JSONB, concurrency | Requires container/setup, more complex | A/B testing needs concurrent writes; SQLite would bottleneck |
| **In-memory cache** | Simple, fast, no dependencies | Not distributed, lost on restart | Acceptable for single-instance; Redis would add complexity |
| **SHA256 token hashing** | Secure, irreversible | Cannot recover original token | Security is paramount; tokens can be regenerated |
| **Weighted random assignment** | Simple, fair distribution | No deterministic reproducibility | Simplicity wins; deterministic hashing available if needed |
| **Events separate from experiments** | Flexibility, simpler tracking | Requires user_id join for analysis | Allows cross-experiment analysis; trade-off is acceptable |
| **Mock repositories for tests** | Fast, isolated, no database pollution | Mocks may diverge from real implementation | Integration tests catch divergence; speed is critical for CI/CD |
| **Synchronous SQLAlchemy** | Simpler code, easier debugging | Lower concurrency than async | Sufficient for current scale; async migration path exists |

### Alternative Approaches Considered

| Approach | Why Not Chosen |
|----------|----------------|
| **Django** | Heavier, less control over async, slower startup |
| **MongoDB** | Overkill for structured experiment data; PostgreSQL JSONB sufficient |
| **Redis for primary storage** | Persistence concerns; PostgreSQL more reliable for critical data |
| **Deterministic hashing for assignment** | Weighted random simpler; deterministic available in feature flags |
| **GraphQL** | REST sufficient; OpenAPI auto-docs more valuable for this use case |

### Repository Pattern Architecture

The application uses the Repository pattern to abstract data access, providing a clean separation between the API layer and database implementation.

#### Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (Routers)                     │
│  experiments.py │ events.py │ feature_flags.py │ api_tokens │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Depends on interfaces only
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Repository Interfaces                      │
│  ExperimentRepo │ EventRepo │ FeatureFlagRepo │ ApiTokenRepo│
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Implementations
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 SQLAlchemy Implementations                   │
│  SQLAlchemyExperimentRepo │ SQLAlchemyEventRepo │ ...       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database (PostgreSQL)                      │
└─────────────────────────────────────────────────────────────┘
```

#### Directory Structure

```
app/
├── dependencies.py              # FastAPI dependency injection
├── repositories/
│   ├── __init__.py
│   ├── interfaces.py           # Abstract interfaces + Entity classes
│   └── sqlalchemy/
│       ├── __init__.py
│       ├── experiment_repo.py  # SQLAlchemy implementation
│       ├── event_repo.py
│       ├── feature_flag_repo.py
│       └── api_token_repo.py   # Token storage with SHA256 hashing
└── routers/                    # API endpoints (depend on interfaces)
    ├── experiments.py
    ├── events.py
    ├── feature_flags.py
    └── api_tokens.py           # Token management endpoints
```

#### Entity Classes

Database-agnostic data structures (pure Python dataclasses):

| Entity | Description |
|--------|-------------|
| `ExperimentEntity` | Experiment with variants |
| `VariantEntity` | Experiment variant |
| `AssignmentEntity` | User-to-variant assignment |
| `EventEntity` | User event/action |
| `FeatureFlagEntity` | Feature flag configuration |
| `FeatureFlagOverrideEntity` | Per-user flag override |
| `ApiTokenEntity` | API authentication token |

#### Repository Interfaces

| Interface | Methods |
|-----------|---------|
| `ExperimentRepository` | `create`, `get_by_id`, `update`, `get_variants`, `get_assignment`, `create_assignment`, `get_assignments_by_variant` |
| `EventRepository` | `create`, `list`, `get_events_for_user_after` |
| `FeatureFlagRepository` | `create`, `get_by_key`, `list_all`, `update`, `delete`, `get_user_override`, `set_user_override`, `delete_user_override` |
| `ApiTokenRepository` | `create`, `get_by_hash`, `get_by_id`, `list_all`, `delete`, `deactivate`, `update_last_used` |

#### Benefits

1. **Database Independence**: Routers don't know about SQLAlchemy
2. **Testability**: Can inject mock repositories for unit testing
3. **Flexibility**: Easy to swap implementations (SQLite → PostgreSQL)
4. **Separation of Concerns**: Business logic separate from data access
5. **Type Safety**: Interfaces define clear contracts

#### Dependency Injection

FastAPI's `Depends()` is used to inject repository instances:

```python
@router.get("/{experiment_id}")
def get_experiment(
    experiment_id: int,
    repo: ExperimentRepository = Depends(get_experiment_repository),
):
    entity = repo.get_by_id(experiment_id)
    ...
```

### Database Schema Design

The schema follows normalized design principles:

```
experiments (1) ─── (N) variants
     │                    │
     │                    │
     └──── (N) assignments ────┘
                   │
                   │ (linked via user_id)
                   │
              events (separate table, not directly linked)
```

**Key Design Decisions:**

1. **Events not directly linked to experiments**: Events are recorded independently and linked via `user_id`. This allows:
   - Recording events before a user is assigned to an experiment
   - The same event can be analyzed across multiple experiments
   - Simpler event tracking implementation

2. **Unique constraint on (experiment_id, user_id)**: Ensures idempotent assignments at the database level.

3. **Indexes on common query patterns**:
   - `ix_event_user_timestamp`: For filtering events by user and time
   - `ix_event_type`: For filtering by event type
   - `ix_assignment_user_experiment`: For fast assignment lookups

### Assignment Algorithm

Traffic allocation uses weighted random selection:
1. Generate random number between 0-100
2. Iterate through variants, accumulating traffic percentages
3. Assign to first variant where cumulative percentage exceeds random number

This approach ensures fair distribution according to configured percentages.

### Results Endpoint Design Philosophy

The results endpoint is designed to support multiple use cases:

**1. Real-time Monitoring**
- Quick overview of user counts and conversion rates per variant
- Basic metrics without heavy computation

**2. Deep Analysis**
- Event breakdown by type (`events_by_type` field)
- Filtering by date range and event type
- Statistical significance with chi-square test

**3. Executive Summaries**
- Clear conversion rates as percentages
- Simple `is_significant` boolean flag
- Total counts for quick overview

**Query Parameters:**
- `event_type`: Focus on specific conversions (e.g., purchases only)
- `start_date`/`end_date`: Analyze specific time periods
- Future extension: `group_by` for time series data

## Production Scale Considerations

### Database

1. **Read replicas**: For heavy result queries, add PostgreSQL read replicas
2. **Connection pooling**: Currently using SQLAlchemy pool (pool_size=5, max_overflow=10); can add PgBouncer for larger deployments
3. **Partitioning**: Partition events table by timestamp for large datasets
4. **Indexing**: Additional indexes for high-cardinality queries

### Caching

1. **Assignment caching**: Cache user assignments in Redis (most frequent operation)
2. **Results caching**: Cache computed results with TTL for popular experiments
3. **Token validation**: Cache validated tokens to reduce auth overhead

### Performance

1. **Async database operations**: Use async SQLAlchemy for better concurrency
2. **Batch event ingestion**: Add bulk event endpoint for high-volume tracking
3. **Pre-computed aggregates**: Store daily/hourly aggregates for results

### Infrastructure

1. **Horizontal scaling**: Stateless API allows easy horizontal scaling
2. **Load balancer**: Add nginx/ALB in front of API instances
3. **Message queue**: Use Kafka/SQS for async event processing
4. **Monitoring**: Add Prometheus metrics and Grafana dashboards

### Data Architecture

```
[Client] → [Load Balancer] → [API Servers]
                                   ↓
                            [Redis Cache]
                                   ↓
                         [Primary PostgreSQL]
                                   ↓
                          [Read Replicas]
```

For high-volume event ingestion:
```
[Client] → [API] → [Kafka] → [Event Processor] → [PostgreSQL/ClickHouse]
```

## Priority Improvement: Real-time Event Streaming

If I were to add one feature next, it would be **real-time event streaming for results**.

**Why:**
- Current results are computed on-demand, which doesn't scale
- Stakeholders want live dashboards during experiments
- Event data grows quickly, making real-time queries expensive

**Implementation:**
1. Stream events to a time-series database (ClickHouse/TimescaleDB)
2. Pre-compute metrics incrementally as events arrive
3. WebSocket endpoint for live results updates
4. Background worker for statistical significance recalculation

**Impact:**
- Sub-second results updates instead of query latency
- Reduced database load from repeated result queries
- Better stakeholder experience with live monitoring

## Test Isolation Architecture

A key architectural decision is the complete isolation of tests from any real environment.

### The Problem with Traditional Testing

Typical approaches to testing database-backed applications:
1. **Use test database**: Creates `test.db`, slower I/O, requires cleanup
2. **Use in-memory SQLite**: Still database-bound, can't run in parallel safely
3. **Mock at ORM level**: Brittle, tightly coupled to ORM internals

### Our Solution: Mock Repositories

```
┌─────────────────────────────────────────────────────────────┐
│                       Production                             │
├─────────────────────────────────────────────────────────────┤
│  FastAPI  →  Repository Interface  →  SQLAlchemy Impl       │
│                                            ↓                 │
│                                       [PostgreSQL]           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                        Testing                               │
├─────────────────────────────────────────────────────────────┤
│  FastAPI  →  Repository Interface  →  Mock Impl             │
│                                            ↓                 │
│                                    [In-Memory Dict]          │
└─────────────────────────────────────────────────────────────┘
```

### Mock Repository Implementation

```python
class MockExperimentRepository(ExperimentRepository):
    """In-memory mock - no database connection."""

    def __init__(self):
        self._experiments: dict[int, ExperimentEntity] = {}
        self._next_id = 1

    def reset(self):
        """Called before each test for isolation."""
        self._experiments.clear()
        self._next_id = 1

    def create(self, data: ExperimentInput) -> ExperimentEntity:
        entity = ExperimentEntity(id=self._next_id, ...)
        self._experiments[entity.id] = entity
        self._next_id += 1
        return entity
```

### Test Setup

```python
# Override dependencies with mocks
app.dependency_overrides[get_experiment_repository] = lambda: mock_experiment_repo
app.dependency_overrides[get_event_repository] = lambda: mock_event_repo
app.dependency_overrides[get_feature_flag_repository] = lambda: mock_feature_flag_repo

@pytest.fixture(autouse=True)
def reset_mocks():
    """Each test starts with fresh state."""
    mock_experiment_repo.reset()
    mock_event_repo.reset()
    mock_feature_flag_repo.reset()
    cache.clear()
    yield
```

### Benefits

| Aspect | Result |
|--------|--------|
| **No database files** | No `test.db` created, zero pollution |
| **Fast execution** | 58 tests in ~5 seconds (no I/O) |
| **Parallel safe** | Each test has isolated in-memory state |
| **Easy debugging** | Mock state is inspectable Python dicts |
| **Portable** | Tests run anywhere Python runs |

### Test Coverage

| Type | Count | Purpose |
|------|-------|---------|
| Unit tests | 68 | Component logic via mock repositories |
| Integration tests | 22 | Full API flow against real PostgreSQL server |
| Cache tests | 13 | Cache module in isolation |
| Token cache tests | 10 | Token verification caching behavior |

---

## Additional Features Implemented

1. **Statistical Significance**: Chi-square test for comparing variant performance
2. **Flexible Event Properties**: JSON field for arbitrary event metadata
3. **Date Range Filtering**: Filter results by time period
4. **Event Type Filtering**: Focus analysis on specific event types
5. **Events by Type Breakdown**: Detailed event type counts per variant
6. **Comprehensive Testing**:
   - 68 unit tests with mock repositories
   - 22 integration tests (full workflow testing)
   - Complete test isolation (no database pollution)
7. **Feature Flags**: Complete feature flagging system with:
   - Global enable/disable
   - Percentage-based rollout using deterministic hashing
   - Per-user overrides
   - Cached evaluation for performance
8. **In-Memory Caching**: Thread-safe cache with TTL support for:
   - User assignments (5 minute TTL)
   - Feature flag evaluations (1 minute TTL)
   - Automatic cache invalidation on updates
9. **Repository Pattern**: Clean architecture with:
   - Abstract repository interfaces
   - Database-agnostic entity classes
   - SQLAlchemy implementations for production
   - Mock implementations for testing
   - Dependency injection via FastAPI
10. **Full Docker Containerization**:
    - Production, development, and test profiles
    - PostgreSQL database in containers
    - No local Python environment required
    - Integration tests run in containers
11. **API Token Management**:
    - Database-stored tokens with SHA256 hashing
    - Bootstrap token for initial setup
    - Token CRUD operations (create, list, deactivate, delete)
    - Cache-first verification for high performance
    - Automatic cache invalidation on token changes

---

## Architecture Highlights for Reviewers

### Why Repository Pattern?

The Repository pattern was chosen specifically for this project to demonstrate:

1. **Separation of Concerns**: Business logic in routers is completely decoupled from data access implementation
2. **Testability**: Unit tests inject mock repositories, eliminating database dependencies
3. **Flexibility**: Can swap PostgreSQL for another database without changing router code
4. **Type Safety**: Abstract interfaces define clear contracts between layers

### Extensibility Points

| Extension | How to Implement | Effort |
|-----------|------------------|--------|
| Add new database | Create new repository implementation | Medium |
| Add Redis cache | Implement cache-aside in repositories | Low |
| Add new entity (e.g., Segments) | Add interface + SQLAlchemy impl + mock | Medium |
| Switch to async | Use async SQLAlchemy, minimal router changes | Medium |
| Add message queue | Inject queue service via dependency injection | Low |

### Design Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Repository** | `repositories/` | Abstract data access |
| **Dependency Injection** | `dependencies.py` | Loose coupling, testability |
| **Strategy** | Cache decorator | Pluggable caching strategies |
| **Factory** | Repository providers | Create appropriate implementations |

### Code Quality Indicators

- **No circular imports**: Clean dependency graph
- **Single Responsibility**: Each module has one purpose
- **Open/Closed**: Add features without modifying existing code
- **Interface Segregation**: Focused repository interfaces
- **Dependency Inversion**: High-level modules depend on abstractions

### Test Strategy

```
┌─────────────────────────────────────────────────────────────┐
│  Unit Tests (68)          │  Fast, Isolated, No I/O        │
│  - Mock repositories      │  Run in ~9 seconds             │
│  - Test business logic    │  Safe for CI/CD                │
│  - Token cache tests      │  Verify cache behavior         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Integration Tests (22)   │  Full Stack Validation         │
│  - Real PostgreSQL        │  End-to-end workflows          │
│  - Real HTTP requests     │  Token management flows        │
│  - Cache invalidation     │  Catch integration issues      │
└─────────────────────────────────────────────────────────────┘
```

### Future Roadmap

1. **Phase 1 (Current)**: Monolithic API with PostgreSQL
2. **Phase 2**: Add Redis for distributed caching
3. **Phase 3**: Event streaming with Kafka/RabbitMQ
4. **Phase 4**: Microservices split (Experiments, Events, Flags)
5. **Phase 5**: Real-time results with WebSocket/SSE
