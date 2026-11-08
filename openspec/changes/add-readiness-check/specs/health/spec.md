## ADDED Requirements

### Requirement: Liveness reports that the process is serving

The system SHALL answer `GET /healthz` with 200 and `{"status": "ok"}` whenever the API process can serve requests. The response SHALL NOT depend on the database or Redis.

#### Scenario: Process is up

- **WHEN** a client requests `/healthz`
- **THEN** the response is 200 with `{"status": "ok"}`

#### Scenario: A dependency is down

- **WHEN** the database or Redis is unreachable and a client requests `/healthz`
- **THEN** the response is still 200

### Requirement: Readiness reports whether the dependencies answer

The system SHALL answer `GET /readyz` with 200 and a body listing `database` and `redis` as `ok` when a trivial query to the database and a ping to Redis both succeed. When either fails, the response SHALL be 503 and the body SHALL list that dependency as `failed`.

#### Scenario: Everything answers

- **WHEN** the database and Redis both respond
- **THEN** `/readyz` returns 200 with `{"status": "ok", "checks": {"database": "ok", "redis": "ok"}}`

#### Scenario: One dependency is down

- **WHEN** Redis does not respond and the database does
- **THEN** `/readyz` returns 503 with `{"status": "failed", "checks": {"database": "ok", "redis": "failed"}}`

#### Scenario: Both are down

- **WHEN** neither responds
- **THEN** `/readyz` returns 503 and lists both as `failed`

### Requirement: A readiness check is bounded and reveals no internals

The system SHALL treat a dependency that has not answered within 2 seconds as failed, and SHALL NOT include exception text, hostnames or connection strings in the `/readyz` response.

#### Scenario: A dependency hangs

- **WHEN** a dependency accepts the connection but never answers
- **THEN** `/readyz` returns 503 within about 2 seconds and lists it as `failed`

#### Scenario: Failure detail stays out of the response

- **WHEN** a check fails with an exception whose message contains a connection string
- **THEN** the response body contains only `failed`, not the message
