"""Unit tests for the A/B Testing API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)
AUTH_HEADER = {"Authorization": "Bearer test-token-123"}


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestAuthentication:
    """Tests for authentication."""

    def test_missing_token(self):
        response = client.post("/experiments", json={})
        assert response.status_code in [401, 403]  # HTTPBearer returns 401 or 403

    def test_invalid_token(self):
        response = client.post(
            "/experiments",
            json={},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_valid_token(self):
        response = client.post(
            "/experiments",
            json={
                "name": "Test Experiment",
                "variants": [
                    {"name": "Control", "traffic_percentage": 50},
                    {"name": "Treatment", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 201


class TestExperiments:
    """Tests for experiment endpoints."""

    def test_create_experiment(self):
        response = client.post(
            "/experiments",
            json={
                "name": "Button Color Test",
                "description": "Testing button colors",
                "variants": [
                    {"name": "Blue", "traffic_percentage": 50},
                    {"name": "Green", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Button Color Test"
        assert len(data["variants"]) == 2

    def test_create_experiment_invalid_traffic(self):
        response = client.post(
            "/experiments",
            json={
                "name": "Invalid Test",
                "variants": [
                    {"name": "A", "traffic_percentage": 30},
                    {"name": "B", "traffic_percentage": 30},
                ],
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 422

    def test_get_experiment(self):
        # Create experiment first
        create_response = client.post(
            "/experiments",
            json={
                "name": "Test",
                "variants": [
                    {"name": "A", "traffic_percentage": 50},
                    {"name": "B", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        experiment_id = create_response.json()["id"]

        # Get experiment
        response = client.get(f"/experiments/{experiment_id}", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert response.json()["name"] == "Test"

    def test_get_nonexistent_experiment(self):
        response = client.get("/experiments/999", headers=AUTH_HEADER)
        assert response.status_code == 404


class TestAssignments:
    """Tests for assignment endpoint."""

    def test_get_assignment(self):
        # Create experiment
        create_response = client.post(
            "/experiments",
            json={
                "name": "Test",
                "variants": [
                    {"name": "Control", "traffic_percentage": 50},
                    {"name": "Treatment", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        experiment_id = create_response.json()["id"]

        # Get assignment
        response = client.get(
            f"/experiments/{experiment_id}/assignment/user123",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 200
        assert response.json()["user_id"] == "user123"
        assert response.json()["variant_name"] in ["Control", "Treatment"]

    def test_assignment_idempotency(self):
        # Create experiment
        create_response = client.post(
            "/experiments",
            json={
                "name": "Test",
                "variants": [
                    {"name": "A", "traffic_percentage": 50},
                    {"name": "B", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        experiment_id = create_response.json()["id"]

        # Get assignment multiple times
        first_response = client.get(
            f"/experiments/{experiment_id}/assignment/user456",
            headers=AUTH_HEADER,
        )
        first_variant = first_response.json()["variant_name"]

        # Call again - should return same variant
        for _ in range(5):
            response = client.get(
                f"/experiments/{experiment_id}/assignment/user456",
                headers=AUTH_HEADER,
            )
            assert response.json()["variant_name"] == first_variant


class TestEvents:
    """Tests for event endpoints."""

    def test_create_event(self):
        response = client.post(
            "/events",
            json={
                "user_id": "user123",
                "event_type": "click",
                "properties": {"button": "signup"},
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == "user123"
        assert data["event_type"] == "click"

    def test_list_events(self):
        # Create some events
        for i in range(3):
            client.post(
                "/events",
                json={"user_id": f"user{i}", "event_type": "click"},
                headers=AUTH_HEADER,
            )

        response = client.get("/events", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_list_events_with_filter(self):
        # Create events with different types
        client.post(
            "/events",
            json={"user_id": "user1", "event_type": "click"},
            headers=AUTH_HEADER,
        )
        client.post(
            "/events",
            json={"user_id": "user1", "event_type": "purchase"},
            headers=AUTH_HEADER,
        )

        response = client.get("/events?event_type=click", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert len(response.json()) == 1


class TestResults:
    """Tests for results endpoint."""

    def test_get_results(self):
        # Create experiment
        create_response = client.post(
            "/experiments",
            json={
                "name": "Test",
                "variants": [
                    {"name": "Control", "traffic_percentage": 50},
                    {"name": "Treatment", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        experiment_id = create_response.json()["id"]

        # Assign some users
        for i in range(10):
            client.get(
                f"/experiments/{experiment_id}/assignment/user{i}",
                headers=AUTH_HEADER,
            )

        # Create some events
        for i in range(5):
            client.post(
                "/events",
                json={"user_id": f"user{i}", "event_type": "click"},
                headers=AUTH_HEADER,
            )

        # Get results
        response = client.get(f"/experiments/{experiment_id}/results", headers=AUTH_HEADER)
        assert response.status_code == 200
        data = response.json()
        assert data["total_users"] == 10
        assert len(data["variants"]) == 2
