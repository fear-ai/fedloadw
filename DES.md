# High‑Level Design

## Architecture Overview
FedLoad is organized around modular components:
- **Monitoring Engine** schedules checks and orchestrates workflows.
- **Site Processor** fetches website content and detects changes.
- **Entity Processor** extracts and enriches entities from new content.
- **Report Generator** produces daily and weekly reports.
- **Data Store** persists content hashes, entities, and configuration.
- **API Gateway** exposes REST endpoints for external access.

Components communicate through function calls within a single deployable service. Future versions may split services into separate containers for scalability.

## Data Flow
1. Configuration is loaded by the Monitoring Engine on startup.
2. Scheduled jobs invoke the Site Processor to fetch pages.
3. When a change is detected, content is sent to the Entity Processor.
4. Processed entities and change records are saved in the Data Store.
5. The Report Generator compiles summaries from stored data and writes HTML reports.
6. API requests read from the Data Store and provide system status or stored entities.

## Key Design Decisions
- **JSON Files** for persistent storage to simplify deployment.
- **Spacy NLP** for entity extraction to balance accuracy and resource use.
- **Hash‑based Change Detection** for efficiency across many sites.
- **FastAPI + Uvicorn** for the REST API to enable asynchronous operations.
- **Docker** for consistent runtime environments and optional containerization.

Security considerations include input validation, HTTPS for external requests, and rate limiting on the API.
