# Python Service Implementation Blueprint: [Service Name]

**Document Purpose:** This document outlines the required architecture, technological standards, and implementation guidelines for developing the core Python service. It serves as the primary specification for the `opencode` team.

## 1. High-Level Architecture
The service must adhere to a strictly separated **Layered Architecture** (similar to Clean/Hexagonal principles) to ensure business logic is decoupled from infrastructure concerns.

**Flow:** `HTTP Request` → `Controller Layer` → `Service Layer` → `Repository Layer` → `Persistence (DB)`

### 1.1 Architectural Layers
*   **Controller:** Handles ingress and egress. Translates HTTP requests/responses into domain operations. *Must not contain business logic.*
*   **Service Layer:** Orchestrates the workflow. Contains all core business rules, validation flow control, and transaction management.
*   **Repository Layer:** Defines interfaces (Protocols) for data access. Abstracts the persistence mechanism from the Service layer.
*   **Data Access / Persistence:** Concrete implementation of Repository interfaces using a SQL library/ORM.
*   **Model / Domain Layer:** Contains the pure business entities and their required behaviors. This layer must be completely independent of framework or database specifics.

## 2. Technology Stack & Dependencies
| Component | Recommended Technology | Purpose | Constraints |
| :--- | :--- | :--- | :--- |
| **Web Framework** | FastAPI | High-performance HTTP service implementation and request validation scaffolding. | Must utilize Dependency Injection (DI) for all external services/repositories. |
| **Data Modeling** | Pydantic v2+ | Used for defining schemas, request bodies, response payloads, and in the Domain Layer for core entity structure. | Enforces Type Safety at boundaries (API I/O). |
| **Persistence** | SQLAlchemy 2.0+ | Provides ORM/SQL abstraction layer. | Repository implementation must exclusively use this interface; direct SQL calls are prohibited outside of this layer. |
| **Type Checking** | MyPy | Static analysis tool for enforcing strict type adherence across the codebase. | Must be integrated into CI/CD pipeline as a mandatory check. |
| **Linting & Formatting** | Ruff / Black | Automated code style enforcement and static code quality checks. | Zero deviation from defined standards allowed (e.g., 88-char line limit). |

## 3. Development Standards: The "How"

### 3.1 Type Safety Enforcement
*   All function signatures, class attributes, and data flows *between layers* must be strictly typed using Python type hints (`typing` module) and Pydantic models where applicable.
*   The Service layer should interact with Domain Models (Pydantic/Python classes), not directly with database ORM objects.

### 3.2 Testing Strategy & Verification Scripts
A multi-level approach is required to ensure reliability:

1.  **Unit Tests:** Focused on isolated functions, methods, and logic within the Service Layer. Repositories should be mocked entirely.
2.  **Integration Tests (Local):** Test the Repository implementation against an in-memory or local SQL instance to ensure schema integrity and query correctness. Services are tested using real repositories but without external HTTP dependencies.
3.  **End-to-End (E2E) Tests:** **Mandatory requirement.** A full Docker Compose stack must be created that spins up the Python Service, required databases, message queues (if any), and other dependent services on distinct ports. E2E tests will hit the public HTTP endpoints of this composed environment to verify complete request flow from ingress to persistence.

#### Manual Verification Scripts
To support development iteration and pre-integration checks, two types of verification scripts are required:

*   **Test Scripts (Functional Check):** Small utility scripts (e.g., using `requests` library) designed for manual or basic automated validation. These scripts will send structured test data to the service endpoints to confirm correct response status codes and payload structure, serving as a quick sanity check before running formal E2E tests.
*   **External Scripts (Third-Party Validation):** Specific scripts dedicated to testing interactions with external services (e.g., LLMs, third-party APIs). These verify the successful transmission of data, adherence to external API specifications, and measurement/logging of success rates or latency provided by those external systems.

### 3.3 Observability: Structured Logging & Tracing
*   **Logging Structure:** All logs must be emitted in **Structured JSON format**. This is required for easy parsing by downstream log aggregators.
*   **OpenTelemetry Principles (Self-Contained):** While external OT collectors are not required, the logging mechanism *must* include fields corresponding to OpenTelemetry standards:
    *   `service_name`: Unique identifier for this service.
    *   `log_level`: (e.g., INFO, ERROR).
    *   `trace_id`: A unique ID generated at the Controller ingress point and passed down through every layer (Service -> Repository).
    *   `span_id`: An ID tracking a specific unit of work within that trace.
    *   **Implementation Note:** Implement these IDs using standard Python logging handlers configured to inject context via `logging.Filter`.

## 4. Deployment & Infrastructure Requirements
### 4.1 Secrets Management
The service must rely solely on **local environment variables and configuration files**. No external cloud secret services are permitted in the initial implementation. All secrets (DB credentials, API keys) must be managed via a `.env` file or equivalent Docker Compose volume injection.

### 4.2 Containerization
A complete `Dockerfile` and an accompanying `docker-compose.yml` are required. The `docker-compose.yml` must define networking to support the E2E testing requirement, allowing services on different ports to communicate seamlessly during test execution.

## Summary Checklist for Implementation:
* [ ] Strict adherence to Layer Separation (Controller/Service/Repository).
* [ ] Mandatory use of Pydantic and MyPy for Type Safety.
* [ ] Full implementation of Structured JSON Logging with Trace IDs.
* [ ] Complete, runnable `docker-compose` setup supporting E2E testing across ports.
* [ ] Repository layer abstracts all persistence details away from the Service Layer.
* [ ] Implementation of designated Test and External Verification scripts.
