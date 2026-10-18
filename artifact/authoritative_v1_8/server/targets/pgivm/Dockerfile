# PostgreSQL 17.10 + pg_ivm v1.16 (commit 22b4b4520a3d2be896f07d3d55fb34772a5ecf8e), built once at S2.
# The resulting image ID and the base image digest are journaled at S2 and must match on every resume.
FROM postgres:17.10-bookworm
ARG PG_IVM_COMMIT=22b4b4520a3d2be896f07d3d55fb34772a5ecf8e
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential postgresql-server-dev-17 git ca-certificates \
 && git clone https://github.com/sraoss/pg_ivm.git /src/pg_ivm \
 && cd /src/pg_ivm && git checkout "$PG_IVM_COMMIT" \
 && test "$(git rev-parse HEAD)" = "$PG_IVM_COMMIT" \
 && make USE_PGXS=1 && make USE_PGXS=1 install \
 && chown -R postgres:postgres /src/pg_ivm \
 && rm -rf /var/lib/apt/lists/*
