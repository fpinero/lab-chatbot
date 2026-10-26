# Architecture

React with strict TypeScript, Tailwind and Vite calls FastAPI under `/api`. FastAPI also serves the compiled frontend. API authentication runs before route dispatch; unknown API paths never receive the SPA shell. The generated TypeScript contract includes the common sanitized error envelope.

SQLite uses WAL, foreign-key enforcement and a busy timeout. Alembic upgrades the schema during application startup. Stable owner identity links independently authenticated device sessions. Tokens have 256 bits of randomness; only SHA-256 token hashes are persisted. Session CSRF tokens remain tied to individual records. Origin checks cover login and authenticated writes.

Authentication uses an Argon2id owner passphrase or verified Cloudflare Access identity. JWT verification fixes RS256, checks issuer/audience/expiry/subject and uses a bounded JWKS cache that supports key rotation. Trusting an identity header alone is prohibited. Optional declarative operator policy values remain private and are never encoded as deployment constants in public source or tests.

Authentication throttles persist in bounded five-minute buckets. A short immediate transaction reserves each attempt before expensive credential verification; password hashing concurrency is limited. Forwarded chains are considered only through configured proxy networks. Uvicorn address rewriting must remain disabled.

The development mock adapter has no network operations and cannot be enabled in production. Live generation is not implemented in this milestone. Later slices introduce immutable run snapshots, transactional spend reservations, durable media jobs and bounded attachment storage. One process and one replica remain the initial target.
