# Interview Feedback

**Date**: 2025-01-15
**Commit at review**: `d787aa5`

## Reviewer Questions

1. Your feature flags use deterministic hashing for rollouts, but experiment assignments use `random.uniform()`. Can you walk me through why the different approaches?

2. If two requests for the same user hit different servers at the same time, what happens for each system (experiments vs feature flags)?
