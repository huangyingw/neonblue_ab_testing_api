# Architecture Documentation

> Detailed architecture documentation for the A/B Testing API.
> For a quick overview, see [DESIGN.md](DESIGN.md).

## Table of Contents

1. [Repository Pattern Architecture](#repository-pattern-architecture)
2. [Database Schema Design](#database-schema-design)
3. [Test Isolation Architecture](#test-isolation-architecture)
4. [Production Scale Considerations](#production-scale-considerations)
5. [Architecture Highlights for Reviewers](#architecture-highlights-for-reviewers)

---

## Repository Pattern Architecture

The application uses the Repository pattern to abstract data access, providing a clean separation between the API layer and database implementation.

### Layer Architecture

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

### Directory Structure

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

### Entity Classes

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

### Repository Interfaces

| Interface | Methods |
|-----------|---------|
| `ExperimentRepository` | `create`, `get_by_id`, `update`, `get_variants`, `get_assignment`, `create_assignment`, `get_assignments_by_variant` |
| `EventRepository` | `create`, `list`, `get_events_for_user_after` |
| `FeatureFlagRepository` | `create`, `get_by_key`, `list_all`, `update`, `delete`, `get_user_override`, `set_user_override`, `delete_user_override` |
| `ApiTokenRepository` | `create`, `get_by_hash`, `get_by_id`, `list_all`, `delete`, `deactivate`, `update_last_used` |

### Benefits

1. **Database Independence**: Routers don't know about SQLAlchemy
2. **Testability**: Can inject mock repositories for unit testing
3. **Flexibility**: Easy to swap implementations (SQLite → PostgreSQL)
4. **Separation of Concerns**: Business logic separate from data access
5. **Type Safety**: Interfaces define clear contracts

### Dependency Injection

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

---

## Database Schema Design

### Entity-Relationship Diagram

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│ experiments │       │   variants  │       │ assignments │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id (PK)     │──1:N──│ id (PK)     │──1:N──│ id (PK)     │
│ name        │       │ experiment_id│       │ experiment_id│
│ description │       │ name        │       │ variant_id  │
│ status      │       │ traffic_%   │       │ user_id     │
│ created_at  │       │ created_at  │       │ assigned_at │
└─────────────┘       └─────────────┘       └─────────────┘
                                                   │
                                            (user_id link)
                                                   │
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   events    │       │feature_flags│       │  api_tokens │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id (PK)     │       │ id (PK)     │──1:N──│ id (PK)     │
│ user_id     │       │ key (UNIQUE)│       │ name        │
│ event_type  │       │ name        │       │ token_hash  │
│ timestamp   │       │ enabled     │       │ is_active   │
│ properties  │       │ rollout_%   │       │ created_at  │
│ (JSONB)     │       │ created_at  │       │ expires_at  │
└─────────────┘       └─────────────┘       └─────────────┘
                            │
                           1:N
                            │
                      ┌─────────────┐
                      │ flag_overrides│
                      ├─────────────┤
                      │ id (PK)     │
                      │ flag_id (FK)│
                      │ user_id     │
                      │ enabled     │
                      └─────────────┘
```

### Normalization Level

The schema follows **Third Normal Form (3NF)**:

| Table | 1NF | 2NF | 3NF | Rationale |
|-------|-----|-----|-----|-----------|
| experiments | ✓ | ✓ | ✓ | Atomic columns, no repeating groups |
| variants | ✓ | ✓ | ✓ | Depends only on experiment_id |
| assignments | ✓ | ✓ | ✓ | Links user to variant in experiment |
| events | ✓ | ✓ | ✓ | Independent entity, JSONB for flexibility |
| feature_flags | ✓ | ✓ | ✓ | Self-contained flag configuration |
| flag_overrides | ✓ | ✓ | ✓ | Depends only on flag_id |

**Denormalization Decision**: `events.properties` uses JSONB for flexible metadata storage. This avoids schema changes for new event attributes while maintaining query capability.

### Index Strategy for Query Efficiency

| Index | Type | Query Pattern | Performance Impact |
|-------|------|---------------|-------------------|
| `ix_event_user_timestamp` | Composite B-tree | `WHERE user_id = ? AND timestamp > ?` | O(log n) for user event lookups |
| `ix_event_type` | B-tree | `WHERE event_type = ?` | Fast event filtering |
| `ix_assignment_user_experiment` | Composite B-tree | `WHERE user_id = ? AND experiment_id = ?` | Idempotent assignment checks |
| `ix_override_user` | B-tree | `WHERE user_id = ?` | Feature flag evaluation |
| `token_hash` | Unique B-tree | `WHERE token_hash = ?` | O(1) token lookup |
| `feature_flags.key` | Unique B-tree | `WHERE key = ?` | Flag lookup by key |

### Data Integrity Constraints

| Constraint | Type | Purpose |
|------------|------|---------|
| `uq_experiment_user` | UNIQUE(experiment_id, user_id) | Ensures idempotent user assignments |
| `uq_flag_user` | UNIQUE(flag_id, user_id) | Prevents duplicate flag overrides |
| `experiments.id → variants.experiment_id` | FK CASCADE | Auto-delete variants with experiment |
| `variants.id → assignments.variant_id` | FK | Referential integrity |
| `feature_flags.id → overrides.flag_id` | FK CASCADE | Auto-delete overrides with flag |

### Query Efficiency Analysis

**Most Frequent Queries:**

1. **Assignment Lookup** (every API request per user)
   ```sql
   SELECT * FROM assignments
   WHERE experiment_id = ? AND user_id = ?
   ```
   - Index: `ix_assignment_user_experiment`
   - Complexity: O(log n)
   - Cached: Yes (5 min TTL)

2. **Event Recording** (high volume)
   ```sql
   INSERT INTO events (user_id, event_type, timestamp, properties)
   VALUES (?, ?, ?, ?)
   ```
   - No index needed for INSERT
   - Complexity: O(1) amortized

3. **Results Aggregation** (less frequent, heavier)
   ```sql
   SELECT e.* FROM events e
   JOIN assignments a ON e.user_id = a.user_id
   WHERE a.experiment_id = ?
     AND e.timestamp > a.assigned_at
   ```
   - Uses: `ix_event_user_timestamp`
   - Optimization: Only counts events AFTER assignment

---

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
| **Fast execution** | 68 tests in ~9 seconds (no I/O) |
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
