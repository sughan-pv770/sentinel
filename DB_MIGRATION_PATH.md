# Database Architecture & Postgres Migration Path

## Current Architecture
In this MVP, SentinelX uses an in-memory dictionary-based `state_store.py` (with a Redis fallback) to manage behavioural baselines and risk state. This was chosen to prioritize zero-latency lookups and simplify the demo setup.

## Production Migration
For production, the ephemeral in-memory state should be migrated to a durable datastore:
- **Hot Data (Risk State & Rolling Baselines):** Redis Cluster (already supported via `SENTINELX_REDIS_URL`).
- **Cold Data (Historical Audits, Incidents, Policies):** PostgreSQL.

Migration Path:
1. Implement a `PostgresStore` adapter in `state_store.py` using `asyncpg` or `SQLAlchemy`.
2. Setup a background sync task to write-behind from Redis to Postgres.
3. Migrate `/sentinelx/incidents` and `/sentinelx/policy` routes to query Postgres directly.
