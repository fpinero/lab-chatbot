# Architecture

React with strict TypeScript and Vite calls a FastAPI application under `/api`. Tailwind provides the styling foundation. FastAPI serves compiled frontend assets in the eventual single-process production topology. Unknown API requests never receive the SPA shell.

A provider interface keeps transport code out of the browser. The bootstrap adapter is deterministic and performs no network operations. Development-only preview routes are temporary, contain no persisted private data and cannot spend credit. Production startup currently fails closed.

The next foundation milestone adds validated authentication, server-side sessions, CSRF protection, SQLite WAL persistence and Alembic migrations before enabling private data or live providers. Later milestones add durable jobs, transactional spend reservations, immutable context snapshots and bounded attachment/media storage. One application process and one replica are the initial operational target.

Provider keys, private operator policies and runtime files remain outside source control and static assets. The public interface must not encode the operator's selected private authentication policy.
