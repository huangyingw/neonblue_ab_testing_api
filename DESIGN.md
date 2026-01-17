# Design Document

> Quick overview of architecture decisions and trade-offs.
> For detailed architecture documentation, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Table of Contents

1. [Technology Choices](#technology-choices)
2. [Trade-offs Analysis](#trade-offs-analysis)
3. [Key Design Decisions](#key-design-decisions)
4. [Features Implemented](#features-implemented)
5. [Future Roadmap](#future-roadmap)

---

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Framework | FastAPI | Modern async Python framework with automatic OpenAPI docs, type hints, and excellent performance |
| Database | PostgreSQL 16 | Production-grade RDBMS with connection pooling, JSONB support for flexible event properties |
| ORM | SQLAlchemy | Industry standard, supports multiple databases, handles connection pooling |
| Validation | Pydantic | Native FastAPI integration, automatic request/response validation |
| Statistics | SciPy | Robust statistical testing library for chi-square significance calculation |
| Architecture | Repository Pattern | Clean separation between API and data access layers |
| Containerization | Docker Compose | Multi-profile setup for production, development, and testing environments |

---

## Trade-offs Analysis

| Decision | Benefits | Trade-offs | Why We Accepted |
|----------|----------|------------|-----------------|
| **Repository Pattern** | Testability, flexibility, clean separation | More boilerplate code | Testing benefits outweigh complexity |
| **PostgreSQL over SQLite** | Production-ready, JSONB, concurrency | Requires container setup | A/B testing needs concurrent writes |
| **In-memory cache** | Simple, fast, no dependencies | Not distributed, lost on restart | Acceptable for single-instance |
| **SHA256 token hashing** | Secure, irreversible | Cannot recover original token | Security is paramount |
| **Mock repositories for tests** | Fast, isolated, no database pollution | Mocks may diverge from real impl | Integration tests catch divergence |

### Alternative Approaches Considered

| Approach | Why Not Chosen |
|----------|----------------|
| Django | Heavier, less control over async, slower startup |
| MongoDB | Overkill for structured data; PostgreSQL JSONB sufficient |
| Redis for primary storage | Persistence concerns; PostgreSQL more reliable |
| GraphQL | REST sufficient; OpenAPI auto-docs more valuable |

---

## Key Design Decisions

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (FastAPI Routers)            │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Depends on interfaces only
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Repository Interfaces (Abstract)               │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
       ┌─────────────┐                 ┌─────────────┐
       │ SQLAlchemy  │                 │    Mock     │
       │    Impl     │                 │    Impl     │
       └─────────────┘                 └─────────────┘
              │                               │
              ▼                               ▼
        [PostgreSQL]                    [In-Memory]
        (Production)                     (Testing)
```

**Key Principles:**
- Routers never import database models directly
- All data access through abstract repository interfaces
- Entity classes are pure Python dataclasses (no ORM dependencies)
- Dependency injection via FastAPI's `Depends()`

> See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed layer architecture, entity classes, and repository interfaces.

### Data Modeling

The schema follows **Third Normal Form (3NF)** with strategic denormalization:
- 7 tables: experiments, variants, assignments, events, feature_flags, flag_overrides, api_tokens
- Composite indexes for frequent query patterns
- JSONB for flexible event metadata
- Unique constraints for idempotent operations

> See [ARCHITECTURE.md](ARCHITECTURE.md#database-schema-design) for ER diagrams, index strategy, and query efficiency analysis.

### Test Isolation

Tests are **completely isolated** from any real environment:
- Mock repositories replace real database access
- Each test starts with fresh in-memory state
- 68 unit tests run in ~9 seconds (no I/O)
- 22 integration tests validate full stack with real PostgreSQL

> See [ARCHITECTURE.md](ARCHITECTURE.md#test-isolation-architecture) for implementation details.

---

## Features Implemented

### Core A/B Testing
- Create experiments with multiple variants and configurable traffic allocation
- Idempotent user-to-variant assignment
- Event recording with flexible JSON properties
- Statistical significance with chi-square test
- Results filtering by date range and event type

### Feature Flags
- Global enable/disable
- Percentage-based rollout using deterministic hashing
- Per-user overrides
- Cached evaluation for performance

### Caching
- Thread-safe in-memory cache with TTL support
- User assignments (5 minute TTL)
- Feature flag evaluations (1 minute TTL)
- Automatic cache invalidation on updates

### API Token Management
- Database-stored tokens with SHA256 hashing
- Bootstrap token for initial setup
- Token CRUD operations (create, list, deactivate, delete)
- Cache-first verification for high performance

### Containerization
- Production, development, and test profiles
- PostgreSQL database in containers
- Integration tests run in containers

---

## Future Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Monolithic API with PostgreSQL | ✅ Current |
| 2 | Add Redis for distributed caching | Planned |
| 3 | Event streaming with Kafka/RabbitMQ | Planned |
| 4 | Microservices split | Planned |
| 5 | Real-time results with WebSocket/SSE | Planned |

### Priority Improvement: Real-time Event Streaming

**Why:** Current results are computed on-demand, which doesn't scale for live monitoring.

**Implementation:**
1. Stream events to a time-series database (ClickHouse/TimescaleDB)
2. Pre-compute metrics incrementally as events arrive
3. WebSocket endpoint for live results updates

---

## Further Reading

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed architecture documentation
  - Repository Pattern implementation
  - Database schema with ER diagrams
  - Index strategy and query efficiency
  - Test isolation architecture
  - Production scale considerations
