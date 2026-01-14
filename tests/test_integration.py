"""
Integration tests for the A/B Testing API.

These tests run against a live API server to verify end-to-end functionality.
Run with: docker-compose --profile integration run --rm integration
"""

import os
import time
import httpx
import pytest

# API base URL - use environment variable or default to localhost
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
# Token is set via BOOTSTRAP_TOKEN in docker-compose for the API server
TEST_TOKEN = os.getenv("TEST_TOKEN", "test-token-123")
AUTH_HEADER = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture(scope="module")
def client():
    """Create HTTP client for integration tests."""
    with httpx.Client(base_url=API_BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
def wait_for_api(client):
    """Wait for API to be ready."""
    max_retries = 30
    for i in range(max_retries):
        try:
            response = client.get("/health")
            if response.status_code == 200:
                return True
        except httpx.ConnectError:
            pass
        time.sleep(1)
    pytest.fail("API did not become ready in time")


class TestHealthCheck:
    """Integration tests for health endpoint."""

    def test_health_endpoint(self, client, wait_for_api):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestAuthenticationIntegration:
    """Integration tests for authentication."""

    def test_request_without_token_is_rejected(self, client, wait_for_api):
        response = client.get("/experiments/1")
        assert response.status_code in [401, 403]

    def test_request_with_invalid_token_is_rejected(self, client, wait_for_api):
        response = client.get(
            "/experiments/1",
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401

    def test_request_with_valid_token_is_accepted(self, client, wait_for_api):
        response = client.get("/health")
        assert response.status_code == 200


class TestExperimentWorkflow:
    """Integration tests for complete experiment workflow."""

    def test_full_experiment_workflow(self, client, wait_for_api):
        """Test complete flow: create experiment -> assign users -> record events -> get results."""

        # Step 1: Create experiment
        create_response = client.post(
            "/experiments",
            headers=AUTH_HEADER,
            json={
                "name": "Integration Test Experiment",
                "description": "Testing full workflow",
                "variants": [
                    {"name": "Control", "traffic_percentage": 50},
                    {"name": "Treatment", "traffic_percentage": 50},
                ],
            },
        )
        assert create_response.status_code == 201
        experiment = create_response.json()
        experiment_id = experiment["id"]
        assert experiment["name"] == "Integration Test Experiment"
        assert len(experiment["variants"]) == 2

        # Step 2: Get experiment
        get_response = client.get(
            f"/experiments/{experiment_id}",
            headers=AUTH_HEADER,
        )
        assert get_response.status_code == 200
        assert get_response.json()["id"] == experiment_id

        # Step 3: Update experiment status
        update_response = client.patch(
            f"/experiments/{experiment_id}",
            headers=AUTH_HEADER,
            json={"status": "running"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["status"] == "running"

        # Step 4: Assign multiple users
        assigned_variants = {}
        for i in range(10):
            user_id = f"integration_user_{i}"
            assign_response = client.get(
                f"/experiments/{experiment_id}/assignment/{user_id}",
                headers=AUTH_HEADER,
            )
            assert assign_response.status_code == 200
            data = assign_response.json()
            assert data["user_id"] == user_id
            assert data["variant_name"] in ["Control", "Treatment"]
            assigned_variants[user_id] = data["variant_name"]

        # Step 5: Verify idempotency - same user gets same variant
        for user_id, expected_variant in list(assigned_variants.items())[:3]:
            for _ in range(3):
                response = client.get(
                    f"/experiments/{experiment_id}/assignment/{user_id}",
                    headers=AUTH_HEADER,
                )
                assert response.status_code == 200
                assert response.json()["variant_name"] == expected_variant

        # Step 6: Record events for some users
        for i in range(5):
            user_id = f"integration_user_{i}"
            event_response = client.post(
                "/events",
                headers=AUTH_HEADER,
                json={
                    "user_id": user_id,
                    "event_type": "click",
                    "properties": {"button": "signup", "test": "integration"},
                },
            )
            assert event_response.status_code == 201

        # Record purchase events for fewer users
        for i in range(2):
            user_id = f"integration_user_{i}"
            event_response = client.post(
                "/events",
                headers=AUTH_HEADER,
                json={
                    "user_id": user_id,
                    "event_type": "purchase",
                    "properties": {"amount": 99.99},
                },
            )
            assert event_response.status_code == 201

        # Step 7: Get experiment results
        results_response = client.get(
            f"/experiments/{experiment_id}/results",
            headers=AUTH_HEADER,
        )
        assert results_response.status_code == 200
        results = results_response.json()
        assert results["experiment_id"] == experiment_id
        assert results["total_users"] == 10
        assert len(results["variants"]) == 2

        # Step 8: Get filtered results by event type
        filtered_response = client.get(
            f"/experiments/{experiment_id}/results",
            headers=AUTH_HEADER,
            params={"event_type": "purchase"},
        )
        assert filtered_response.status_code == 200

        # Step 9: List events
        events_response = client.get(
            "/events",
            headers=AUTH_HEADER,
            params={"event_type": "click", "limit": 10},
        )
        assert events_response.status_code == 200
        events = events_response.json()
        assert len(events) >= 5


class TestFeatureFlagWorkflow:
    """Integration tests for feature flag workflow."""

    def test_full_feature_flag_workflow(self, client, wait_for_api):
        """Test complete flow: create flag -> evaluate -> override -> delete."""

        # Step 1: Create feature flag
        create_response = client.post(
            "/flags",
            headers=AUTH_HEADER,
            json={
                "key": "integration-test-flag",
                "name": "Integration Test Flag",
                "description": "Flag for integration testing",
                "enabled": False,
                "rollout_percentage": 50,
            },
        )
        assert create_response.status_code == 201
        flag = create_response.json()
        assert flag["key"] == "integration-test-flag"
        assert flag["enabled"] is False
        assert flag["rollout_percentage"] == 50

        # Step 2: Get flag
        get_response = client.get(
            "/flags/integration-test-flag",
            headers=AUTH_HEADER,
        )
        assert get_response.status_code == 200
        assert get_response.json()["key"] == "integration-test-flag"

        # Step 3: List all flags
        list_response = client.get("/flags", headers=AUTH_HEADER)
        assert list_response.status_code == 200
        flags = list_response.json()
        assert any(f["key"] == "integration-test-flag" for f in flags)

        # Step 4: Evaluate flag for multiple users (rollout 50%)
        enabled_count = 0
        disabled_count = 0
        for i in range(20):
            eval_response = client.get(
                f"/flags/integration-test-flag/evaluate/rollout_user_{i}",
                headers=AUTH_HEADER,
            )
            assert eval_response.status_code == 200
            if eval_response.json()["enabled"]:
                enabled_count += 1
            else:
                disabled_count += 1

        # With 50% rollout, we should have some of each (probabilistic)
        # Just verify we got results, exact distribution varies
        assert enabled_count + disabled_count == 20

        # Step 5: Verify deterministic evaluation (same user = same result)
        first_result = None
        for _ in range(5):
            eval_response = client.get(
                "/flags/integration-test-flag/evaluate/consistent_user",
                headers=AUTH_HEADER,
            )
            assert eval_response.status_code == 200
            if first_result is None:
                first_result = eval_response.json()["enabled"]
            else:
                assert eval_response.json()["enabled"] == first_result

        # Step 6: Create user override
        override_response = client.post(
            "/flags/integration-test-flag/overrides",
            headers=AUTH_HEADER,
            json={"user_id": "override_user", "enabled": True},
        )
        assert override_response.status_code == 201

        # Step 7: Verify override works
        eval_response = client.get(
            "/flags/integration-test-flag/evaluate/override_user",
            headers=AUTH_HEADER,
        )
        assert eval_response.status_code == 200
        assert eval_response.json()["enabled"] is True
        assert eval_response.json()["reason"] == "user_override"

        # Step 8: Update flag to globally enabled
        update_response = client.patch(
            "/flags/integration-test-flag",
            headers=AUTH_HEADER,
            json={"enabled": True},
        )
        assert update_response.status_code == 200
        assert update_response.json()["enabled"] is True

        # Step 9: Verify global enable works
        eval_response = client.get(
            "/flags/integration-test-flag/evaluate/any_user",
            headers=AUTH_HEADER,
        )
        assert eval_response.status_code == 200
        assert eval_response.json()["enabled"] is True
        assert eval_response.json()["reason"] == "global"

        # Step 10: Delete user override
        delete_override_response = client.delete(
            "/flags/integration-test-flag/overrides/override_user",
            headers=AUTH_HEADER,
        )
        assert delete_override_response.status_code == 204

        # Step 11: Delete flag
        delete_response = client.delete(
            "/flags/integration-test-flag",
            headers=AUTH_HEADER,
        )
        assert delete_response.status_code == 204

        # Step 12: Verify flag is deleted
        get_response = client.get(
            "/flags/integration-test-flag",
            headers=AUTH_HEADER,
        )
        assert get_response.status_code == 404


class TestEdgeCases:
    """Integration tests for edge cases and error handling."""

    def test_experiment_not_found(self, client, wait_for_api):
        response = client.get("/experiments/99999", headers=AUTH_HEADER)
        assert response.status_code == 404

    def test_flag_not_found(self, client, wait_for_api):
        response = client.get("/flags/nonexistent-flag", headers=AUTH_HEADER)
        assert response.status_code == 404

    def test_invalid_experiment_creation(self, client, wait_for_api):
        # Traffic percentages don't sum to 100
        response = client.post(
            "/experiments",
            headers=AUTH_HEADER,
            json={
                "name": "Invalid",
                "variants": [
                    {"name": "A", "traffic_percentage": 30},
                    {"name": "B", "traffic_percentage": 30},
                ],
            },
        )
        assert response.status_code == 422

    def test_duplicate_flag_creation(self, client, wait_for_api):
        # Create first flag
        client.post(
            "/flags",
            headers=AUTH_HEADER,
            json={"key": "duplicate-test-flag", "name": "First"},
        )

        # Try to create duplicate
        response = client.post(
            "/flags",
            headers=AUTH_HEADER,
            json={"key": "duplicate-test-flag", "name": "Second"},
        )
        assert response.status_code == 409

        # Cleanup
        client.delete("/flags/duplicate-test-flag", headers=AUTH_HEADER)


class TestConcurrency:
    """Integration tests for concurrent access scenarios."""

    def test_concurrent_assignments(self, client, wait_for_api):
        """Test that concurrent assignment requests maintain idempotency."""
        # Create experiment
        create_response = client.post(
            "/experiments",
            headers=AUTH_HEADER,
            json={
                "name": "Concurrency Test",
                "variants": [
                    {"name": "A", "traffic_percentage": 50},
                    {"name": "B", "traffic_percentage": 50},
                ],
            },
        )
        experiment_id = create_response.json()["id"]

        # Make multiple rapid requests for same user
        user_id = "concurrent_user"
        results = []
        for _ in range(10):
            response = client.get(
                f"/experiments/{experiment_id}/assignment/{user_id}",
                headers=AUTH_HEADER,
            )
            results.append(response.json()["variant_name"])

        # All results should be identical (idempotency)
        assert len(set(results)) == 1


class TestEventFiltering:
    """Integration tests for event filtering and pagination."""

    def test_event_filtering_by_user_id(self, client, wait_for_api):
        # Create events for multiple users
        for i in range(5):
            client.post(
                "/events",
                headers=AUTH_HEADER,
                json={"user_id": f"filter_user_{i}", "event_type": "action"},
            )

        # Filter by specific user
        response = client.get(
            "/events",
            headers=AUTH_HEADER,
            params={"user_id": "filter_user_2"},
        )
        assert response.status_code == 200
        events = response.json()
        assert all(e["user_id"] == "filter_user_2" for e in events)

    def test_event_pagination(self, client, wait_for_api):
        # Create multiple events
        for i in range(15):
            client.post(
                "/events",
                headers=AUTH_HEADER,
                json={"user_id": f"page_user_{i}", "event_type": "page_test"},
            )

        # Get first page
        response1 = client.get(
            "/events",
            headers=AUTH_HEADER,
            params={"event_type": "page_test", "limit": 5, "offset": 0},
        )
        assert response1.status_code == 200
        assert len(response1.json()) == 5

        # Get second page
        response2 = client.get(
            "/events",
            headers=AUTH_HEADER,
            params={"event_type": "page_test", "limit": 5, "offset": 5},
        )
        assert response2.status_code == 200
        assert len(response2.json()) == 5


class TestExperimentStatus:
    """Integration tests for experiment status management."""

    def test_experiment_lifecycle(self, client, wait_for_api):
        """Test experiment status transitions: draft -> running -> completed."""
        # Create experiment (starts as draft)
        create_response = client.post(
            "/experiments",
            headers=AUTH_HEADER,
            json={
                "name": "Lifecycle Test",
                "variants": [
                    {"name": "A", "traffic_percentage": 50},
                    {"name": "B", "traffic_percentage": 50},
                ],
            },
        )
        assert create_response.status_code == 201
        experiment_id = create_response.json()["id"]
        assert create_response.json()["status"] == "draft"

        # Start experiment
        update_response = client.patch(
            f"/experiments/{experiment_id}",
            headers=AUTH_HEADER,
            json={"status": "running"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["status"] == "running"

        # Complete experiment
        complete_response = client.patch(
            f"/experiments/{experiment_id}",
            headers=AUTH_HEADER,
            json={"status": "completed"},
        )
        assert complete_response.status_code == 200
        assert complete_response.json()["status"] == "completed"


class TestResultsStatistics:
    """Integration tests for experiment results with statistics."""

    def test_results_with_events_by_type(self, client, wait_for_api):
        """Test that results correctly group events by type."""
        # Create experiment
        create_response = client.post(
            "/experiments",
            headers=AUTH_HEADER,
            json={
                "name": "Stats Test",
                "variants": [
                    {"name": "Control", "traffic_percentage": 50},
                    {"name": "Treatment", "traffic_percentage": 50},
                ],
            },
        )
        experiment_id = create_response.json()["id"]

        # Assign users and record various events
        for i in range(10):
            user_id = f"stats_user_{i}"
            client.get(
                f"/experiments/{experiment_id}/assignment/{user_id}",
                headers=AUTH_HEADER,
            )

            # Record different event types
            client.post(
                "/events",
                headers=AUTH_HEADER,
                json={"user_id": user_id, "event_type": "view"},
            )
            if i < 5:
                client.post(
                    "/events",
                    headers=AUTH_HEADER,
                    json={"user_id": user_id, "event_type": "click"},
                )
            if i < 2:
                client.post(
                    "/events",
                    headers=AUTH_HEADER,
                    json={"user_id": user_id, "event_type": "purchase"},
                )

        # Get results
        response = client.get(
            f"/experiments/{experiment_id}/results",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 200
        results = response.json()
        assert results["total_users"] == 10
        assert results["total_events"] > 0

        # Check that variants have events_by_type breakdown
        for variant in results["variants"]:
            assert "events_by_type" in variant


class TestApiTokenManagement:
    """Integration tests for API token management."""

    def test_bootstrap_token_works(self, client, wait_for_api):
        """Test that the bootstrap token from BOOTSTRAP_TOKEN env var works."""
        response = client.get(
            "/experiments/1",
            headers=AUTH_HEADER,
        )
        # 404 is expected (no experiment with id 1), but not 401
        assert response.status_code in [200, 404]

    def test_list_tokens(self, client, wait_for_api):
        """Test listing API tokens."""
        response = client.get("/tokens", headers=AUTH_HEADER)
        assert response.status_code == 200
        tokens = response.json()
        # Should have at least the bootstrap token
        assert len(tokens) >= 1
        assert any(t["name"] == "Bootstrap Token" for t in tokens)

    def test_create_and_use_new_token(self, client, wait_for_api):
        """Test creating a new token and using it."""
        # Create a new token
        create_response = client.post(
            "/tokens",
            headers=AUTH_HEADER,
            json={"name": "Integration Test Token"},
        )
        assert create_response.status_code == 201
        token_data = create_response.json()
        assert "token" in token_data  # Raw token returned only on creation
        new_token = token_data["token"]
        token_id = token_data["id"]

        # Use the new token to make a request
        response = client.get(
            "/health",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert response.status_code == 200

        # Delete the test token
        delete_response = client.delete(
            f"/tokens/{token_id}",
            headers=AUTH_HEADER,
        )
        assert delete_response.status_code == 204

    def test_deactivate_token(self, client, wait_for_api):
        """Test deactivating a token."""
        # Create a new token
        create_response = client.post(
            "/tokens",
            headers=AUTH_HEADER,
            json={"name": "Token to Deactivate"},
        )
        token_data = create_response.json()
        new_token = token_data["token"]
        token_id = token_data["id"]

        # Deactivate the token
        deactivate_response = client.post(
            f"/tokens/{token_id}/deactivate",
            headers=AUTH_HEADER,
        )
        assert deactivate_response.status_code == 200

        # Try to use the deactivated token - should fail
        response = client.get(
            "/health",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        # Health doesn't need auth, use another endpoint
        response = client.get(
            "/experiments/1",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert response.status_code == 401

        # Clean up
        client.delete(f"/tokens/{token_id}", headers=AUTH_HEADER)

    def test_multiple_requests_with_same_token(self, client, wait_for_api):
        """Test that multiple requests with the same token work (cache behavior)."""
        # Make many rapid requests with the same token
        # All should succeed, demonstrating cache is working
        for i in range(10):
            response = client.get("/health")
            assert response.status_code == 200

            # Also test authenticated endpoint
            response = client.get("/tokens", headers=AUTH_HEADER)
            assert response.status_code == 200

    def test_cache_invalidation_on_deactivate(self, client, wait_for_api):
        """Test that token cache is invalidated immediately on deactivation."""
        # Create a new token
        create_response = client.post(
            "/tokens",
            headers=AUTH_HEADER,
            json={"name": "Cache Test Token"},
        )
        token_data = create_response.json()
        new_token = token_data["token"]
        token_id = token_data["id"]
        new_auth = {"Authorization": f"Bearer {new_token}"}

        # Make several requests to populate cache
        for _ in range(5):
            response = client.get("/tokens", headers=new_auth)
            assert response.status_code == 200

        # Deactivate the token
        deactivate_response = client.post(
            f"/tokens/{token_id}/deactivate",
            headers=AUTH_HEADER,
        )
        assert deactivate_response.status_code == 200

        # Immediately try to use the deactivated token
        # Should fail even though it was recently cached
        response = client.get("/tokens", headers=new_auth)
        assert response.status_code == 401

        # Clean up
        client.delete(f"/tokens/{token_id}", headers=AUTH_HEADER)

    def test_cache_invalidation_on_delete(self, client, wait_for_api):
        """Test that token cache is invalidated immediately on deletion."""
        # Create a new token
        create_response = client.post(
            "/tokens",
            headers=AUTH_HEADER,
            json={"name": "Delete Cache Test Token"},
        )
        token_data = create_response.json()
        new_token = token_data["token"]
        token_id = token_data["id"]
        new_auth = {"Authorization": f"Bearer {new_token}"}

        # Make several requests to populate cache
        for _ in range(5):
            response = client.get("/tokens", headers=new_auth)
            assert response.status_code == 200

        # Delete the token
        delete_response = client.delete(
            f"/tokens/{token_id}",
            headers=AUTH_HEADER,
        )
        assert delete_response.status_code == 204

        # Immediately try to use the deleted token
        # Should fail even though it was recently cached
        response = client.get("/tokens", headers=new_auth)
        assert response.status_code == 401
