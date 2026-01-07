# Design Document

## Architecture Decisions and Trade-offs

### Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Framework | FastAPI | Modern async Python framework with automatic OpenAPI docs, type hints, and excellent performance |
| Database | SQLite | Simple, file-based, zero configuration. Easy to swap for PostgreSQL in production |
| ORM | SQLAlchemy | Industry standard, supports multiple databases, handles connection pooling |
| Validation | Pydantic | Native FastAPI integration, automatic request/response validation |
| Statistics | SciPy | Robust statistical testing library for chi-square significance calculation |

### Database Schema Design

The schema follows normalized design principles:

```
experiments (1) ─── (N) variants
     │                    │
     │                    │
     └──── (N) assignments ────┘
                   │
                   │ (linked via user_id)
                   │
              events (separate table, not directly linked)
```

**Key Design Decisions:**

1. **Events not directly linked to experiments**: Events are recorded independently and linked via `user_id`. This allows:
   - Recording events before a user is assigned to an experiment
   - The same event can be analyzed across multiple experiments
   - Simpler event tracking implementation

2. **Unique constraint on (experiment_id, user_id)**: Ensures idempotent assignments at the database level.

3. **Indexes on common query patterns**:
   - `ix_event_user_timestamp`: For filtering events by user and time
   - `ix_event_type`: For filtering by event type
   - `ix_assignment_user_experiment`: For fast assignment lookups

### Assignment Algorithm

Traffic allocation uses weighted random selection:
1. Generate random number between 0-100
2. Iterate through variants, accumulating traffic percentages
3. Assign to first variant where cumulative percentage exceeds random number

This approach ensures fair distribution according to configured percentages.

### Results Endpoint Design Philosophy

The results endpoint is designed to support multiple use cases:

**1. Real-time Monitoring**
- Quick overview of user counts and conversion rates per variant
- Basic metrics without heavy computation

**2. Deep Analysis**
- Event breakdown by type (`events_by_type` field)
- Filtering by date range and event type
- Statistical significance with chi-square test

**3. Executive Summaries**
- Clear conversion rates as percentages
- Simple `is_significant` boolean flag
- Total counts for quick overview

**Query Parameters:**
- `event_type`: Focus on specific conversions (e.g., purchases only)
- `start_date`/`end_date`: Analyze specific time periods
- Future extension: `group_by` for time series data

## Production Scale Considerations

### Database

1. **Migrate to PostgreSQL**: Better concurrency, more robust for production
2. **Read replicas**: For heavy result queries
3. **Connection pooling**: Use PgBouncer or SQLAlchemy pool settings
4. **Partitioning**: Partition events table by timestamp for large datasets

### Caching

1. **Assignment caching**: Cache user assignments in Redis (most frequent operation)
2. **Results caching**: Cache computed results with TTL for popular experiments
3. **Token validation**: Cache validated tokens to reduce auth overhead

### Performance

1. **Async database operations**: Use async SQLAlchemy for better concurrency
2. **Batch event ingestion**: Add bulk event endpoint for high-volume tracking
3. **Pre-computed aggregates**: Store daily/hourly aggregates for results

### Infrastructure

1. **Horizontal scaling**: Stateless API allows easy horizontal scaling
2. **Load balancer**: Add nginx/ALB in front of API instances
3. **Message queue**: Use Kafka/SQS for async event processing
4. **Monitoring**: Add Prometheus metrics and Grafana dashboards

### Data Architecture

```
[Client] → [Load Balancer] → [API Servers]
                                   ↓
                            [Redis Cache]
                                   ↓
                         [Primary PostgreSQL]
                                   ↓
                          [Read Replicas]
```

For high-volume event ingestion:
```
[Client] → [API] → [Kafka] → [Event Processor] → [PostgreSQL/ClickHouse]
```

## Priority Improvement: Real-time Event Streaming

If I were to add one feature next, it would be **real-time event streaming for results**.

**Why:**
- Current results are computed on-demand, which doesn't scale
- Stakeholders want live dashboards during experiments
- Event data grows quickly, making real-time queries expensive

**Implementation:**
1. Stream events to a time-series database (ClickHouse/TimescaleDB)
2. Pre-compute metrics incrementally as events arrive
3. WebSocket endpoint for live results updates
4. Background worker for statistical significance recalculation

**Impact:**
- Sub-second results updates instead of query latency
- Reduced database load from repeated result queries
- Better stakeholder experience with live monitoring

## Additional Features Implemented

1. **Statistical Significance**: Chi-square test for comparing variant performance
2. **Flexible Event Properties**: JSON field for arbitrary event metadata
3. **Date Range Filtering**: Filter results by time period
4. **Event Type Filtering**: Focus analysis on specific event types
5. **Events by Type Breakdown**: Detailed event type counts per variant
6. **Unit Tests**: Comprehensive test coverage for critical paths
