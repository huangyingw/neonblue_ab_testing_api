"""Unit tests for the A/B Testing API.

These tests use mock repositories and are completely isolated from any database.
No real database is touched during test execution.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import (
    get_experiment_repository,
    get_event_repository,
    get_feature_flag_repository,
)
from app.cache import cache
from tests.mocks import (
    MockExperimentRepository,
    MockEventRepository,
    MockFeatureFlagRepository,
)


# Create mock repository instances
mock_experiment_repo = MockExperimentRepository()
mock_event_repo = MockEventRepository()
mock_feature_flag_repo = MockFeatureFlagRepository()


def override_experiment_repository():
    """Provide mock experiment repository."""
    return mock_experiment_repo


def override_event_repository():
    """Provide mock event repository."""
    return mock_event_repo


def override_feature_flag_repository():
    """Provide mock feature flag repository."""
    return mock_feature_flag_repo


# Override dependencies with mocks
app.dependency_overrides[get_experiment_repository] = override_experiment_repository
app.dependency_overrides[get_event_repository] = override_event_repository
app.dependency_overrides[get_feature_flag_repository] = override_feature_flag_repository


client = TestClient(app)
AUTH_HEADER = {"Authorization": "Bearer test-token-123"}


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all mock repositories and cache before each test."""
    mock_experiment_repo.reset()
    mock_event_repo.reset()
    mock_feature_flag_repo.reset()
    cache.clear()
    yield


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
        assert response.status_code in [401, 403]

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

    def test_update_experiment(self):
        # Create experiment first
        create_response = client.post(
            "/experiments",
            json={
                "name": "Original Name",
                "description": "Original description",
                "variants": [
                    {"name": "A", "traffic_percentage": 50},
                    {"name": "B", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        experiment_id = create_response.json()["id"]

        # Update experiment
        response = client.patch(
            f"/experiments/{experiment_id}",
            json={"name": "Updated Name", "status": "running"},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"
        assert response.json()["status"] == "running"

    def test_update_nonexistent_experiment(self):
        response = client.patch(
            "/experiments/999",
            json={"name": "New Name"},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 404

    def test_create_experiment_with_three_variants(self):
        response = client.post(
            "/experiments",
            json={
                "name": "Three Variant Test",
                "variants": [
                    {"name": "Control", "traffic_percentage": 33},
                    {"name": "Treatment A", "traffic_percentage": 33},
                    {"name": "Treatment B", "traffic_percentage": 34},
                ],
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 201
        assert len(response.json()["variants"]) == 3


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

    def test_assignment_nonexistent_experiment(self):
        response = client.get(
            "/experiments/999/assignment/user123",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 404

    def test_assignment_multiple_users_distribution(self):
        # Create experiment
        create_response = client.post(
            "/experiments",
            json={
                "name": "Distribution Test",
                "variants": [
                    {"name": "Control", "traffic_percentage": 50},
                    {"name": "Treatment", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        experiment_id = create_response.json()["id"]

        # Assign 100 users
        variants_count = {"Control": 0, "Treatment": 0}
        for i in range(100):
            response = client.get(
                f"/experiments/{experiment_id}/assignment/dist_user_{i}",
                headers=AUTH_HEADER,
            )
            variant_name = response.json()["variant_name"]
            variants_count[variant_name] += 1

        # With 50/50 split, both should have users
        assert variants_count["Control"] > 0
        assert variants_count["Treatment"] > 0


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

    def test_list_events_with_user_id_filter(self):
        # Create events for different users
        for i in range(3):
            client.post(
                "/events",
                json={"user_id": f"filter_user_{i}", "event_type": "click"},
                headers=AUTH_HEADER,
            )

        response = client.get("/events?user_id=filter_user_1", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["user_id"] == "filter_user_1"

    def test_list_events_with_pagination(self):
        # Create multiple events
        for i in range(10):
            client.post(
                "/events",
                json={"user_id": f"page_user_{i}", "event_type": "view"},
                headers=AUTH_HEADER,
            )

        # Test limit
        response = client.get("/events?limit=3", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert len(response.json()) == 3

        # Test offset
        response = client.get("/events?limit=3&offset=3", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_create_event_with_custom_timestamp(self):
        custom_timestamp = "2024-01-01T12:00:00"
        response = client.post(
            "/events",
            json={
                "user_id": "timestamp_user",
                "event_type": "custom_event",
                "timestamp": custom_timestamp,
                "properties": {"source": "test"},
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 201
        assert "2024-01-01" in response.json()["timestamp"]

    def test_create_event_with_complex_properties(self):
        response = client.post(
            "/events",
            json={
                "user_id": "props_user",
                "event_type": "purchase",
                "properties": {
                    "amount": 99.99,
                    "currency": "USD",
                    "items": ["item1", "item2"],
                    "metadata": {"source": "web", "version": "1.0"},
                },
            },
            headers=AUTH_HEADER,
        )
        assert response.status_code == 201
        props = response.json()["properties"]
        assert props["amount"] == 99.99
        assert props["items"] == ["item1", "item2"]


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

    def test_get_results_nonexistent_experiment(self):
        response = client.get("/experiments/999/results", headers=AUTH_HEADER)
        assert response.status_code == 404

    def test_get_results_with_event_type_filter(self):
        # Create experiment
        create_response = client.post(
            "/experiments",
            json={
                "name": "Results Filter Test",
                "variants": [
                    {"name": "Control", "traffic_percentage": 50},
                    {"name": "Treatment", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        experiment_id = create_response.json()["id"]

        # Assign users
        for i in range(4):
            client.get(
                f"/experiments/{experiment_id}/assignment/results_user_{i}",
                headers=AUTH_HEADER,
            )

        # Create different event types
        for i in range(2):
            client.post(
                "/events",
                json={"user_id": f"results_user_{i}", "event_type": "click"},
                headers=AUTH_HEADER,
            )
        for i in range(2, 4):
            client.post(
                "/events",
                json={"user_id": f"results_user_{i}", "event_type": "purchase"},
                headers=AUTH_HEADER,
            )

        # Filter by event type
        response = client.get(
            f"/experiments/{experiment_id}/results?event_type=click",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 200

    def test_get_results_with_statistical_significance(self):
        # Create experiment
        create_response = client.post(
            "/experiments",
            json={
                "name": "Significance Test",
                "variants": [
                    {"name": "Control", "traffic_percentage": 50},
                    {"name": "Treatment", "traffic_percentage": 50},
                ],
            },
            headers=AUTH_HEADER,
        )
        experiment_id = create_response.json()["id"]

        # Assign many users to get statistical data
        for i in range(50):
            client.get(
                f"/experiments/{experiment_id}/assignment/sig_user_{i}",
                headers=AUTH_HEADER,
            )

        # Create events for some users
        for i in range(25):
            client.post(
                "/events",
                json={"user_id": f"sig_user_{i}", "event_type": "conversion"},
                headers=AUTH_HEADER,
            )

        # Get results - should include statistical significance
        response = client.get(f"/experiments/{experiment_id}/results", headers=AUTH_HEADER)
        assert response.status_code == 200
        data = response.json()
        assert data["total_users"] == 50


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

    def test_get_nonexistent_flag(self):
        response = client.get("/flags/nonexistent-flag", headers=AUTH_HEADER)
        assert response.status_code == 404

    def test_update_nonexistent_flag(self):
        response = client.patch(
            "/flags/nonexistent-flag",
            json={"enabled": True},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 404

    def test_delete_nonexistent_flag(self):
        response = client.delete("/flags/nonexistent-flag", headers=AUTH_HEADER)
        assert response.status_code == 404

    def test_evaluate_flag_rollout(self):
        # Create flag with 50% rollout
        client.post(
            "/flags",
            json={
                "key": "rollout-flag",
                "name": "Rollout Test",
                "enabled": False,
                "rollout_percentage": 50,
            },
            headers=AUTH_HEADER,
        )

        # Evaluate for multiple users
        enabled_count = 0
        for i in range(100):
            response = client.get(
                f"/flags/rollout-flag/evaluate/rollout_user_{i}",
                headers=AUTH_HEADER,
            )
            assert response.status_code == 200
            if response.json()["enabled"]:
                enabled_count += 1
                assert response.json()["reason"] == "rollout"

        # Should have some enabled and some disabled
        assert enabled_count > 0
        assert enabled_count < 100

    def test_evaluate_flag_deterministic(self):
        # Create flag with rollout
        client.post(
            "/flags",
            json={
                "key": "deterministic-flag",
                "name": "Deterministic Test",
                "enabled": False,
                "rollout_percentage": 50,
            },
            headers=AUTH_HEADER,
        )

        # Same user should get same result every time
        first_result = None
        for _ in range(10):
            response = client.get(
                "/flags/deterministic-flag/evaluate/same_user",
                headers=AUTH_HEADER,
            )
            if first_result is None:
                first_result = response.json()["enabled"]
            else:
                assert response.json()["enabled"] == first_result

    def test_evaluate_nonexistent_flag(self):
        response = client.get(
            "/flags/nonexistent/evaluate/user123",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 404

    def test_update_existing_override(self):
        # Create flag
        client.post(
            "/flags",
            json={"key": "update-override-flag", "name": "Update Override Test"},
            headers=AUTH_HEADER,
        )

        # Create override
        client.post(
            "/flags/update-override-flag/overrides",
            json={"user_id": "override_user", "enabled": True},
            headers=AUTH_HEADER,
        )

        # Update override
        client.post(
            "/flags/update-override-flag/overrides",
            json={"user_id": "override_user", "enabled": False},
            headers=AUTH_HEADER,
        )

        # Verify updated
        response = client.get(
            "/flags/update-override-flag/evaluate/override_user",
            headers=AUTH_HEADER,
        )
        assert response.json()["enabled"] is False
        assert response.json()["reason"] == "user_override"

    def test_create_override_nonexistent_flag(self):
        response = client.post(
            "/flags/nonexistent-flag/overrides",
            json={"user_id": "user123", "enabled": True},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 404

    def test_delete_override(self):
        # Create flag
        client.post(
            "/flags",
            json={"key": "delete-override-flag", "name": "Delete Override Test"},
            headers=AUTH_HEADER,
        )

        # Create override
        client.post(
            "/flags/delete-override-flag/overrides",
            json={"user_id": "delete_user", "enabled": True},
            headers=AUTH_HEADER,
        )

        # Delete override
        response = client.delete(
            "/flags/delete-override-flag/overrides/delete_user",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 204

    def test_delete_override_nonexistent_flag(self):
        response = client.delete(
            "/flags/nonexistent-flag/overrides/user123",
            headers=AUTH_HEADER,
        )
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
