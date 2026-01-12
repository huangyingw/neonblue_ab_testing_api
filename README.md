# A/B Testing API

A production-ready experimentation platform API for managing A/B tests, user assignments, and event tracking.

## Project Highlights

> **For Reviewers**: Key architectural decisions and engineering practices demonstrated in this project.

| Aspect | Implementation | Why It Matters |
|--------|---------------|----------------|
| **Architecture** | Repository Pattern | Decouples business logic from data access; enables easy database swapping |
| **Test Isolation** | Mock Repositories | Tests run without database; fully isolated, no environment pollution |
| **Test Coverage** | 58 unit + 16 integration tests | Comprehensive coverage with fast execution |
| **Data Layer** | Abstract Interfaces + SQLAlchemy | Database-agnostic entities; clear contracts |
| **Containerization** | Full Docker support | Production, dev, test profiles; no local setup needed |
| **Statistics** | Chi-square significance | Real statistical rigor for experiment analysis |

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
│   ExperimentRepository │ EventRepository │ FeatureFlagRepo  │
└─────────────────────────────────────────────────────────────┘
             │                                    │
     ┌───────┴───────┐                    ┌──────┴──────┐
     ▼               ▼                    ▼             ▼
┌─────────┐    ┌─────────┐         ┌─────────┐   ┌─────────┐
│SQLAlchemy│   │  Mock   │         │SQLAlchemy│  │  Mock   │
│  Impl   │    │  Impl   │         │  Impl   │   │  Impl   │
└─────────┘    └─────────┘         └─────────┘   └─────────┘
     │              │
     ▼              ▼
 [Database]    [In-Memory]
(Production)    (Testing)
```

**Key Design Decisions:**
- Routers never import database models directly
- All data access through abstract repository interfaces
- Entity classes are pure Python dataclasses (no ORM dependencies)
- Dependency injection via FastAPI's `Depends()`

### Test Isolation Strategy

Tests are **completely isolated** from any real environment:

```python
# Mock repositories replace real database access
app.dependency_overrides[get_experiment_repository] = lambda: mock_experiment_repo
app.dependency_overrides[get_event_repository] = lambda: mock_event_repo

# Each test starts with fresh state
@pytest.fixture(autouse=True)
def reset_mocks():
    mock_experiment_repo.reset()
    mock_event_repo.reset()
    cache.clear()
```

**Benefits:**
- No `test.db` created - zero database pollution
- Tests run in ~5 seconds (no I/O overhead)
- Safe for parallel execution
- Easy to add new test scenarios

---

## Features

- Create experiments with multiple variants and configurable traffic allocation
- Idempotent user-to-variant assignment
- Event recording with flexible JSON properties
- Experiment results with statistical significance calculation
- **Feature flags** with rollout percentages and user overrides
- **In-memory caching** with TTL for performance
- Bearer token authentication
- Docker deployment support

## Quick Start (Docker)

```bash
# Production mode
docker compose up --build

# Development mode (with hot reload)
docker compose --profile dev up --build dev

# Run unit tests
docker compose --profile test run --rm test

# Run integration tests (starts API server and runs tests against it)
docker compose --profile integration up --abort-on-container-exit
```

The API will be available at `http://localhost:8000`.

## API Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Authentication

All endpoints (except `/health`) require Bearer token authentication:

```bash
curl -H "Authorization: Bearer test-token-123" http://localhost:8000/experiments
```

Default tokens: `test-token-123`, `test-token-456`

## API Endpoints

### Experiments

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/experiments` | Create a new experiment |
| GET | `/experiments/{id}` | Get experiment by ID |
| PATCH | `/experiments/{id}` | Update experiment |
| GET | `/experiments/{id}/assignment/{user_id}` | Get/create user assignment |
| GET | `/experiments/{id}/results` | Get experiment results |

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events` | Record an event |
| GET | `/events` | List events with filters |

### Feature Flags

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/flags` | Create a feature flag |
| GET | `/flags` | List all feature flags |
| GET | `/flags/{key}` | Get flag by key |
| PATCH | `/flags/{key}` | Update flag |
| DELETE | `/flags/{key}` | Delete flag |
| GET | `/flags/{key}/evaluate/{user_id}` | Evaluate flag for user |
| POST | `/flags/{key}/overrides` | Create user override |
| DELETE | `/flags/{key}/overrides/{user_id}` | Delete user override |

## Example Usage

### Create an Experiment

```bash
curl -X POST http://localhost:8000/experiments \
  -H "Authorization: Bearer test-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Button Color Test",
    "description": "Testing button colors",
    "variants": [
      {"name": "Control (Blue)", "traffic_percentage": 50},
      {"name": "Treatment (Green)", "traffic_percentage": 50}
    ]
  }'
```

### Get User Assignment (Idempotent)

```bash
# First call - assigns user to a variant
curl http://localhost:8000/experiments/1/assignment/user123 \
  -H "Authorization: Bearer test-token-123"

# Subsequent calls return the same assignment
curl http://localhost:8000/experiments/1/assignment/user123 \
  -H "Authorization: Bearer test-token-123"
```

### Record an Event

```bash
curl -X POST http://localhost:8000/events \
  -H "Authorization: Bearer test-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "event_type": "purchase",
    "properties": {"amount": 99.99, "product": "premium"}
  }'
```

### Get Experiment Results

```bash
# All results
curl http://localhost:8000/experiments/1/results \
  -H "Authorization: Bearer test-token-123"

# Filter by event type
curl "http://localhost:8000/experiments/1/results?event_type=purchase" \
  -H "Authorization: Bearer test-token-123"
```

### Create a Feature Flag

```bash
curl -X POST http://localhost:8000/flags \
  -H "Authorization: Bearer test-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "dark-mode",
    "name": "Dark Mode",
    "enabled": false,
    "rollout_percentage": 25
  }'
```

### Evaluate Feature Flag for User

```bash
curl http://localhost:8000/flags/dark-mode/evaluate/user123 \
  -H "Authorization: Bearer test-token-123"
```

## Running Tests

### Unit Tests (58 tests, ~5 seconds)

Tests use mock repositories - no database required:

```bash
# In Docker
docker compose --profile test run --rm test

# Or locally with Python
python3 -m pytest tests/test_api.py tests/test_cache.py -v
```

### Integration Tests (16 tests)

Full end-to-end tests against a live API server:

```bash
docker compose --profile integration up --abort-on-container-exit

# Clean up
docker compose --profile integration down
```

**Test Categories:**
- Health check endpoint
- Authentication (missing/invalid/valid tokens)
- Full experiment workflow (create -> assign -> events -> results)
- Full feature flag workflow (CRUD, evaluation, overrides)
- Edge cases and error handling
- Concurrent access and idempotency

## Project Structure

```
├── app/
│   ├── main.py               # FastAPI application entry point
│   ├── config.py             # Configuration settings
│   ├── auth.py               # Authentication middleware
│   ├── cache.py              # In-memory cache with TTL
│   ├── database.py           # Database connection
│   ├── dependencies.py       # FastAPI dependency injection
│   ├── models.py             # SQLAlchemy ORM models
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── repositories/
│   │   ├── interfaces.py     # Abstract interfaces + Entity classes
│   │   └── sqlalchemy/       # SQLAlchemy implementations
│   │       ├── experiment_repo.py
│   │       ├── event_repo.py
│   │       └── feature_flag_repo.py
│   └── routers/
│       ├── experiments.py    # Experiment endpoints
│       ├── events.py         # Event endpoints
│       └── feature_flags.py  # Feature flag endpoints
├── tests/
│   ├── test_api.py           # Unit tests (mock-based)
│   ├── test_cache.py         # Cache unit tests
│   ├── test_integration.py   # Integration tests
│   └── mocks/                # Mock repository implementations
│       ├── __init__.py
│       └── repositories.py
├── docs/
│   └── diagrams/             # PlantUML architecture diagrams
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── DESIGN.md                 # Detailed design documentation
```

## Further Documentation

See [DESIGN.md](DESIGN.md) for:
- Detailed architecture decisions and trade-offs
- Database schema design rationale
- Production scaling considerations
- Future improvement roadmap
