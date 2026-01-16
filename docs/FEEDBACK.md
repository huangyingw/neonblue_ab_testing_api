# Interview Feedback

## Reviewer Questions

### Question 1: Different Approaches for Randomization

> Your feature flags use deterministic hashing for rollouts, but experiment assignments use `random.uniform()`. Can you walk me through why the different approaches?

### Question 2: Concurrent Requests

> If two requests for the same user hit different servers at the same time, what happens for each system (experiments vs feature flags)?

---

## Analysis

### Current Implementation

#### Experiment Assignment (`app/routers/experiments.py`)

```python
# Line 176: Uses random.uniform() for traffic allocation
rand = random.uniform(0, 100)
cumulative = 0.0
for variant in variants:
    cumulative += variant.traffic_percentage
    if rand <= cumulative:
        assigned_variant = variant
        break
```

**Commit**: `86a4da4` - Implement A/B testing API with full feature set

#### Feature Flag Rollout (`app/routers/feature_flags.py`)

```python
# Lines 201-205: Uses deterministic hash for rollout
hash_input = f"{key}:{user_id}"
hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
bucket = hash_value % 100
if bucket < flag.rollout_percentage:
    return True
```

**Commit**: `beed270` - Add feature flags and in-memory caching

---

### Why Different Approaches?

| Aspect | Experiment Assignment | Feature Flag Rollout |
|--------|----------------------|---------------------|
| **Algorithm** | `random.uniform()` | Deterministic MD5 hash |
| **Consistency** | Relies on database persistence | Hash ensures same result |
| **Idempotency** | Database constraint enforces | Algorithm itself is idempotent |
| **Purpose** | One-time assignment (stored) | Repeated evaluation (computed) |

**Reasoning**:

1. **Experiments**: The assignment is stored in database after first random selection. Subsequent requests read from database, ensuring idempotency.

2. **Feature Flags**: No database storage for evaluation results. Deterministic hashing ensures the same user always gets the same result without database lookup.

---

### Concurrent Request Behavior

#### Scenario: Two requests for same user hit different servers simultaneously

| System | Behavior | Outcome |
|--------|----------|---------|
| **Experiments** | Both generate random numbers → both try to INSERT → **database unique constraint** prevents duplicate → only one succeeds, second gets existing assignment | ✅ Safe - database handles race condition |
| **Feature Flags** | Both compute hash → both get **identical result** (deterministic) | ✅ Safe - algorithm is deterministic |

**Key Insight**: Both systems are safe for concurrent access, but through different mechanisms:
- Experiments: Database-level protection (unique constraint on `experiment_id + user_id`)
- Feature Flags: Algorithm-level protection (deterministic hashing)

---

## Relevant Commits

| Commit | Description |
|--------|-------------|
| `86a4da4` | Initial experiment assignment with random.uniform() |
| `beed270` | Feature flags with deterministic hashing |
| `07fc7cb` | Repository pattern refactoring |

---

## Potential Improvements

### Option 1: Unify to Deterministic Hashing

Change experiment assignment to use deterministic hashing like feature flags:

```python
# Proposed change for experiments
hash_input = f"{experiment_id}:{user_id}"
hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
bucket = hash_value % 100

cumulative = 0.0
for variant in variants:
    cumulative += variant.traffic_percentage
    if bucket <= cumulative:
        assigned_variant = variant
        break
```

**Pros**:
- Consistent approach across systems
- Predictable assignments (same user always gets same variant)
- Reduces database race conditions

**Cons**:
- Cannot reassign users (would need to change experiment ID)
- Less random distribution (hash-based)

### Option 2: Keep Current Design (Recommended)

The current design is intentional:

1. **Experiments need flexibility**: Admins may want to clear assignments and re-randomize
2. **Feature flags need speed**: No database lookup for evaluation
3. **Both are safe**: Different mechanisms, same result (idempotent)

---

## Response Draft

> Hi,
>
> Thank you for the detailed review questions!
>
> **Why different approaches?**
>
> The difference is intentional based on the persistence model:
>
> - **Experiments**: Assignments are stored in the database. We use `random.uniform()` for the initial selection, then the database becomes the source of truth. The unique constraint on `(experiment_id, user_id)` ensures idempotency.
>
> - **Feature Flags**: Evaluations are not stored. We use deterministic hashing so the same user always gets the same result without database lookup, enabling high-performance evaluation.
>
> **Concurrent requests scenario:**
>
> - **Experiments**: Two concurrent requests would both try to INSERT. The database unique constraint ensures only one succeeds; the second request gets the existing assignment. Safe via database-level locking.
>
> - **Feature Flags**: Both requests compute the same hash and get identical results. Safe via algorithmic determinism.
>
> Both systems handle concurrent access correctly, just through different mechanisms appropriate to their storage models.
