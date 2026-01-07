# A/B Testing API

A simplified experimentation platform API for managing A/B tests, user assignments, and event tracking.

## Features

- Create experiments with multiple variants and configurable traffic allocation
- Idempotent user-to-variant assignment
- Event recording with flexible properties
- Experiment results with statistical significance calculation
- Bearer token authentication
- Docker deployment support

## Quick Start

### Option 1: Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload
```

### Option 2: Docker

```bash
# Build and run with docker-compose
docker-compose up --build

# Or build manually
docker build -t ab-testing-api .
docker run -p 8000:8000 ab-testing-api
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

## Running Tests

```bash
pytest tests/ -v
```

## Demo Script

Run the interactive demo to see all endpoints in action:

```bash
# Start the server first, then:
./examples/demo.sh
```

## Project Structure

```
├── app/
│   ├── main.py           # FastAPI application
│   ├── config.py         # Configuration settings
│   ├── auth.py           # Authentication middleware
│   ├── database.py       # Database connection
│   ├── models.py         # SQLAlchemy models
│   ├── schemas.py        # Pydantic schemas
│   └── routers/
│       ├── experiments.py
│       └── events.py
├── tests/
│   └── test_api.py
├── examples/
│   └── demo.sh
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── DESIGN.md
```
