#!/bin/bash

# A/B Testing API Demo Script
# This script demonstrates all API endpoints with curl commands

BASE_URL="http://localhost:8000"
TOKEN="test-token-123"
AUTH="Authorization: Bearer $TOKEN"

echo "=== A/B Testing API Demo ==="
echo ""

# 1. Health Check
echo "1. Health Check"
curl -s "$BASE_URL/health" | jq
echo ""

# 2. Create an experiment
echo "2. Create Experiment"
EXPERIMENT=$(curl -s -X POST "$BASE_URL/experiments" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Button Color Test",
    "description": "Testing which button color drives more conversions",
    "variants": [
      {"name": "Control (Blue)", "traffic_percentage": 50},
      {"name": "Treatment (Green)", "traffic_percentage": 50}
    ]
  }')
echo "$EXPERIMENT" | jq
EXPERIMENT_ID=$(echo "$EXPERIMENT" | jq -r '.id')
echo ""

# 3. Get experiment details
echo "3. Get Experiment Details"
curl -s "$BASE_URL/experiments/$EXPERIMENT_ID" -H "$AUTH" | jq
echo ""

# 4. Update experiment status to running
echo "4. Update Experiment Status"
curl -s -X PATCH "$BASE_URL/experiments/$EXPERIMENT_ID" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"status": "running"}' | jq
echo ""

# 5. Assign users to variants (demonstrate idempotency)
echo "5. Assign Users to Variants"
echo "First assignment for user1:"
ASSIGNMENT1=$(curl -s "$BASE_URL/experiments/$EXPERIMENT_ID/assignment/user1" -H "$AUTH")
echo "$ASSIGNMENT1" | jq
VARIANT1=$(echo "$ASSIGNMENT1" | jq -r '.variant_name')

echo ""
echo "Second assignment for user1 (should be same variant - idempotent):"
ASSIGNMENT2=$(curl -s "$BASE_URL/experiments/$EXPERIMENT_ID/assignment/user1" -H "$AUTH")
echo "$ASSIGNMENT2" | jq
VARIANT2=$(echo "$ASSIGNMENT2" | jq -r '.variant_name')

if [ "$VARIANT1" = "$VARIANT2" ]; then
  echo "✓ Idempotency verified: Both assignments returned '$VARIANT1'"
else
  echo "✗ Idempotency failed!"
fi
echo ""

# Assign more users
echo "Assigning 20 more users..."
for i in $(seq 2 21); do
  curl -s "$BASE_URL/experiments/$EXPERIMENT_ID/assignment/user$i" -H "$AUTH" > /dev/null
done
echo "Done"
echo ""

# 6. Record events
echo "6. Record Events"
echo "Recording click events..."
curl -s -X POST "$BASE_URL/events" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user1",
    "event_type": "click",
    "properties": {"button": "signup", "page": "homepage"}
  }' | jq

# Record more events
for i in $(seq 1 10); do
  curl -s -X POST "$BASE_URL/events" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"user$i\", \"event_type\": \"click\"}" > /dev/null
done

for i in $(seq 1 5); do
  curl -s -X POST "$BASE_URL/events" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"user$i\", \"event_type\": \"purchase\", \"properties\": {\"amount\": $((RANDOM % 100 + 10))}}" > /dev/null
done
echo "Recorded click and purchase events for multiple users"
echo ""

# 7. List events
echo "7. List Events (with filter)"
curl -s "$BASE_URL/events?event_type=purchase&limit=5" -H "$AUTH" | jq
echo ""

# 8. Get experiment results
echo "8. Get Experiment Results"
curl -s "$BASE_URL/experiments/$EXPERIMENT_ID/results" -H "$AUTH" | jq
echo ""

# 9. Get results filtered by event type
echo "9. Get Results (filtered by purchase events)"
curl -s "$BASE_URL/experiments/$EXPERIMENT_ID/results?event_type=purchase" -H "$AUTH" | jq
echo ""

echo "=== Demo Complete ==="
echo ""
echo "API Documentation available at: $BASE_URL/docs"
