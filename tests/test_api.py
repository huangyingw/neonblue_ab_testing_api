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


class TestFeatureFlags:
    """Tests for feature flag endpoints."""

    def test_create_feature_flag(self):
        response = client.post(
            "/flags",
            json={
                "key": "new-feature",
                "name": "New Feature",
                "description": "A new feature flag",
                "enabled": False,
                "rollout_percentage": 0,
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["key"] == "new-feature"
        assert data["enabled"] is False

    def test_create_duplicate_flag(self):
        # Create first flag
        client.post(
            "/flags",
            json={"key": "duplicate-flag", "name": "Test"},
            headers=AUTH_HEADER,
        )
        # Try to create duplicate
        response = client.post(
            "/flags",
            json={"key": "duplicate-flag", "name": "Test 2"},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 409

    def test_list_feature_flags(self):
        # Create some flags
        for i in range(3):
            client.post(
                "/flags",
                json={"key": f"list-flag-{i}", "name": f"Flag {i}"},
                headers=AUTH_HEADER,
            )

        response = client.get("/flags", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert len(response.json()) >= 3

    def test_update_feature_flag(self):
        # Create flag
        client.post(
            "/flags",
            json={"key": "update-flag", "name": "Original"},
            headers=AUTH_HEADER,
        )

        # Update flag
        response = client.patch(
            "/flags/update-flag",
            json={"enabled": True, "rollout_percentage": 50},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True
        assert response.json()["rollout_percentage"] == 50

    def test_evaluate_flag_disabled(self):
        # Create disabled flag
        client.post(
            "/flags",
            json={"key": "disabled-flag", "name": "Disabled", "enabled": False},
            headers=AUTH_HEADER,
        )

        response = client.get("/flags/disabled-flag/evaluate/user123", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert response.json()["enabled"] is False
        assert response.json()["reason"] == "disabled"

    def test_evaluate_flag_enabled(self):
        # Create enabled flag
        client.post(
            "/flags",
            json={"key": "enabled-flag", "name": "Enabled", "enabled": True},
            headers=AUTH_HEADER,
        )

        response = client.get("/flags/enabled-flag/evaluate/user123", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert response.json()["enabled"] is True
        assert response.json()["reason"] == "global"

    def test_evaluate_flag_with_override(self):
        # Create disabled flag
        client.post(
            "/flags",
            json={"key": "override-flag", "name": "Override Test", "enabled": False},
            headers=AUTH_HEADER,
        )

        # Create user override
        client.post(
            "/flags/override-flag/overrides",
            json={"user_id": "special-user", "enabled": True},
            headers=AUTH_HEADER,
        )

        # Evaluate for special user
        response = client.get("/flags/override-flag/evaluate/special-user", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert response.json()["enabled"] is True
        assert response.json()["reason"] == "user_override"

        # Evaluate for other user
        response = client.get("/flags/override-flag/evaluate/other-user", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_delete_feature_flag(self):
        # Create flag
        client.post(
            "/flags",
            json={"key": "delete-flag", "name": "To Delete"},
            headers=AUTH_HEADER,
        )

        # Delete flag
        response = client.delete("/flags/delete-flag", headers=AUTH_HEADER)
        assert response.status_code == 204

        # Verify deleted
        response = client.get("/flags/delete-flag", headers=AUTH_HEADER)
        assert response.status_code == 404


class TestCache:
    """Tests for caching functionality."""

    def test_assignment_caching(self):
        # Create experiment
        create_response = client.post(
            "/experiments",
            json={
                "name": "Cache Test",
                "variants": [
                    {"name": "A", "traffic_percentage": 50},
                    {"name": "B", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        experiment_id = create_response.json()["id"]

        # First request - creates assignment
        response1 = client.get(
            f"/experiments/{experiment_id}/assignment/cache-user",
            headers=AUTH_HEADER,
        )
        assert response1.status_code == 200
        variant1 = response1.json()["variant_name"]

        # Subsequent requests should return cached result
        for _ in range(10):
            response = client.get(
                f"/experiments/{experiment_id}/assignment/cache-user",
                headers=AUTH_HEADER,
            )
            assert response.json()["variant_name"] == variant1
