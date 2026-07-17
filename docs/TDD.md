# Recall — Full Feature Breakdown + Required Skills, Tools & Knowledge

This lists every feature across both phases, with the concrete skills/tools/knowledge you'll need to build each one. No architecture or code decisions — just the "what you'll need to know/use" for each piece.

---

## PHASE 1 — Core Personal App

### 1. User accounts & authentication (register, login, JWT)
**Features needed:**
- Registration endpoint (email + password)
- Login endpoint returning an access token
- Password hashing at signup
- Token verification on protected endpoints
- "Get current logged-in user" dependency usable across the app

**Skills/tools/knowledge:**
- FastAPI path operations and dependency injection
- Pydantic (request/response schemas, validation)
- Password hashing library (e.g., passlib/bcrypt concepts)
- JWT concepts: encoding/decoding, expiry, secret keys
- OAuth2 password flow (as used by FastAPI's OAuth2PasswordRequestForm)
- HTTP status codes (401/403 vs 404 vs 400) and when each applies

---

### 2. Folders (create, nest, list, rename, delete)
**Features needed:**
- CRUD endpoints for folders
- Folder ownership tied to a user
- Nested/sub-folder support (a folder can live inside another folder)
- Listing folders with their sub-folder hierarchy

**Skills/tools/knowledge:**
- SQLAlchemy models and relationships
- Self-referential foreign keys (a table referencing its own primary key)
- Recursive or hierarchical data querying concepts (even a simple version)
- Basic authorization checks (only the owner can rename/delete)

---

### 3. Notes (create, view, edit, delete; support raw text/PDF/URL sources)
**Features needed:**
- CRUD endpoints for notes within a folder
- Support for different note "source types" (plain text now, extendable to PDF/URL text extraction later)
- Basic content validation (length limits, required fields)

**Skills/tools/knowledge:**
- SQLAlchemy relationships (Folder → Notes, one-to-many)
- Pydantic schema design, including optional fields and enums (for source_type)
- Text extraction libraries if you ingest PDFs/URLs later (e.g., a PDF-parsing library, or simple web scraping/HTML-to-text extraction) — not required for the text-only MVP, but good to know these exist for later
- File upload handling in FastAPI (if you allow uploading PDFs directly)

---

### 4. AI-generated flashcards (agent reads note → proposes cards)
**Features needed:**
- Endpoint to trigger card generation from a note
- Agent logic that reads note content and produces structured flashcard proposals (front/back pairs)
- Cards created in a "pending" state, not visible in the live review queue yet
- Handling failures gracefully (e.g., AI call times out or returns malformed output)

**Skills/tools/knowledge:**
- Your existing LangChain/LangGraph experience
- Structured output generation from an LLM (getting reliably formatted front/back pairs rather than free text)
- Prompt design for flashcard generation specifically (concise, testable Q&A pairs vs. vague ones)
- Async programming in Python (since LLM calls are I/O-bound and you likely don't want to block the API while waiting)
- Background task handling in FastAPI (so card generation doesn't hang the HTTP request)
- Error handling/retries around external API calls
- Since you're keeping the LLM provider undecided: whichever provider you land on, you'll need its Python SDK and API key management regardless

---

### 5. Card review & editing workflow (approve/edit/reject pending cards)
**Features needed:**
- Endpoint(s) to list pending cards awaiting review
- Approve endpoint (moves card to "active" status)
- Edit endpoint (modify front/back text before or after approval)
- Reject/delete endpoint
- Ownership enforcement (can't touch another user's pending cards)

**Skills/tools/knowledge:**
- CRUD/update patterns in FastAPI
- Status/state field design (pending/approved/rejected) and transitions between them
- Authorization logic reused from earlier ("only your own resource")

---

### 6. Spaced repetition scheduling (FSRS algorithm)
**Features needed:**
- A scheduling record per card tracking memory state (stability, difficulty, due date, repetition count, lapses)
- Endpoint to submit a review (user rates recall as again/hard/good/easy)
- Logic that recalculates the next due date and memory parameters after each review
- Handling first-time reviews (card has no prior scheduling state yet) vs. repeat reviews

**Skills/tools/knowledge:**
- The FSRS algorithm itself (you'll need to study its formulas — this is a distinct, non-trivial piece of learning outside the course, likely from FSRS's public spec/reference implementations)
- Python: implementing numerical formulas cleanly, likely as a standalone module separate from your API code
- Unit testing mindset: since this is pure math/logic, it's the ideal candidate for isolated, dependency-free testing
- Date/time handling in Python (calculating "due dates" correctly, timezones if relevant)

---

### 7. Due-cards queries (what's due today, filterable by folder)
**Features needed:**
- Endpoint returning cards due for review, optionally filtered by folder
- Sorting (e.g., most overdue first)
- Pagination or limits so you don't get an unbounded list

**Skills/tools/knowledge:**
- SQL fundamentals: WHERE clauses, date comparisons, ORDER BY, LIMIT/OFFSET
- SQLAlchemy query building across multiple related tables
- FastAPI query parameters (optional filters, defaults, validation on things like folder_id)

---

### 8. Weekly cross-subject recall routine
**Features needed:**
- Endpoint that pulls a due-card batch spanning every folder/subject, not just one
- Some logic to balance the batch (e.g., a cap per subject so one folder doesn't dominate the session)
- Optionally, a way to mark "this was this week's recall session" for tracking habit consistency

**Skills/tools/knowledge:**
- More advanced SQL joins across folders/notes/cards/scheduling tables
- Basic algorithmic thinking for "balanced sampling" across categories (not a course topic, just general logic)
- Query parameter design for session size, subject caps, etc.

---

### 9. "Like" a card
**Features needed:**
- Endpoint to like/unlike a card
- A way to list your liked cards
- Simple table linking user to card

**Skills/tools/knowledge:**
- Many-to-many / junction table pattern in SQLAlchemy
- Composite keys or unique constraints (a user can only like a given card once)

---

### 10. Database schema evolution
**Features needed:**
- Ability to add new tables/columns without destroying existing data as the project grows (e.g., adding the FSRS scheduling table after cards already exist)

**Skills/tools/knowledge:**
- Alembic (migration generation, upgrade/downgrade scripts)
- Understanding of schema versioning and why raw `create_all()` isn't sufficient once you have real data

---

### 11. Environment variables & configuration
**Features needed:**
- Centralized, secure handling of: database connection string, JWT secret key, LLM API key(s)
- Different config for local dev vs. testing vs. production

**Skills/tools/knowledge:**
- `.env` file usage and a settings-loading pattern (e.g., Pydantic's settings management or python-dotenv)
- Basic security hygiene: never committing secrets to version control

---

### 12. CORS
**Features needed:**
- Configuring the API to accept requests from your future frontend's origin

**Skills/tools/knowledge:**
- FastAPI's CORS middleware
- Understanding what CORS actually protects against (so you configure it correctly rather than just "allow all" everywhere)

---

### 13. Automated testing
**Features needed:**
- Test suite covering: FSRS scheduling math (many input combinations), CRUD endpoints, auth flows, and the AI card-generation endpoint using a mocked/fake LLM response
- A dedicated test database that's created fresh and torn down per test run
- Fixtures for common setup (test user, authenticated client, sample folder/notes/cards)

**Skills/tools/knowledge:**
- pytest fundamentals: fixtures, parametrize, assertions, testing exceptions
- FastAPI's TestClient
- Mocking (patching out the real LLM API call so tests are fast, deterministic, and free)
- Test database setup/teardown patterns (often a separate test Postgres instance or schema)

---

### 14. CI/CD pipeline
**Features needed:**
- Pipeline that runs on every push: installs dependencies, spins up a test database, runs the full test suite, builds a Docker image
- Secure handling of secrets in CI (DB credentials, LLM API key)
- Pipeline fails loudly on any broken test

**Skills/tools/knowledge:**
- GitHub Actions: workflow YAML syntax, jobs, steps, service containers (for spinning up Postgres in CI)
- GitHub Secrets management
- Understanding how CI environments differ from your local dev environment (fresh installs every run, no persisted state)

---

### 15. Containerization
**Features needed:**
- API packaged into a container
- Postgres running in its own container
- The two connected and able to communicate
- Persisted data across container restarts (so you don't lose your database on every rebuild)

**Skills/tools/knowledge:**
- Docker fundamentals: writing a Dockerfile, image layers, build context
- Docker Compose: multi-service orchestration, networking between containers, environment variable injection
- Volumes/bind mounts for data persistence
- Docker Hub (or another registry) for pushing/pulling images

---

### 16. Deployment — three paths

**16a. Heroku**
**Skills/tools/knowledge:**
- Heroku CLI and app creation
- Procfile syntax
- Heroku Postgres add-on and its connection string handling
- Environment/config vars on Heroku
- Running Alembic migrations against a remote database

**16b. Docker Compose (self-hosted anywhere)**
**Skills/tools/knowledge:**
- Same Docker/Compose skills as above, applied to a real deployment target (a VM, or even locally as a "production-like" environment)
- Managing environment-specific config (dev vs prod compose files)

**16c. Raw Ubuntu VM (generic cloud provider — up to you which one)**
**Skills/tools/knowledge:**
- Basic Linux server administration: package management, creating a non-root user, SSH
- Installing and configuring Postgres directly on a VM, including setting passwords and access rules
- Running your app as a persistent background service (systemd unit files)
- Gunicorn (or a similar process manager) to run your FastAPI app in production
- Nginx as a reverse proxy in front of your app
- Domain name configuration (pointing a domain at your server)
- SSL/HTTPS setup (e.g., via Let's Encrypt/Certbot)
- Firewall configuration (allowing only necessary ports)
- Since you haven't picked a provider: the concepts are identical across AWS EC2/DigitalOcean/GCP — the only provider-specific piece is initial VM creation and firewall/security-group setup in that provider's console, which you can pick up quickly once you choose one

---

## PHASE 2 — Community Layer

### 17. Public/shareable folders
**Features needed:**
- A flag/field marking a folder as public vs private
- Endpoint to toggle this
- Ensuring private folders never leak into any public-facing endpoint

**Skills/tools/knowledge:**
- Boolean field design and filtering logic in queries (never accidentally exposing private data — a good place to be paranoid and write a test specifically for this)

---

### 18. Browsing & cloning shared decks
**Features needed:**
- Endpoint to list/browse public folders from other users
- "Clone" action that copies a public folder's notes and cards into your own account as a new, independent copy

**Skills/tools/knowledge:**
- Read-only query design for public-facing data
- Transactional thinking: cloning multiple related rows (folder + its notes + its cards) should either fully succeed or fully fail, not partially copy — this touches on database transactions
- SQLAlchemy session/transaction handling

---

### 19. Upvoting/downvoting shared decks
**Features needed:**
- Vote endpoint (up/down) on a public folder
- Preventing duplicate votes from the same user (or allowing vote changes, your choice)
- Aggregating vote counts for display

**Skills/tools/knowledge:**
- Many-to-many/junction table pattern (same concept as "likes," reused for decks)
- SQL aggregation (COUNT, SUM, or a computed score) across a joined query

---

### 20. Following other users
**Features needed:**
- Follow/unfollow endpoint
- List of who you follow / who follows you

**Skills/tools/knowledge:**
- Self-referential many-to-many relationship (users following users) — a distinct pattern from the folder self-reference in Phase 1, since here it's a join table rather than a direct parent-id column

---

### 21. Sorted/filterable public feed
**Features needed:**
- Feed endpoint combining public folders + their owner info + their vote counts
- Sorting by popularity (vote count)
- Optional filter to only show content from users you follow
- Pagination

**Skills/tools/knowledge:**
- Multi-table joins (folders + users + votes + follows, all in one query)
- SQL aggregation combined with filtering and sorting in a single query
- FastAPI query parameter design for sort/filter/pagination options together
- This is the single most complex query in the whole project — good target for query optimization thinking (e.g., indexes on frequently filtered/sorted columns) if you want to go a bit beyond the course

---

## Cross-cutting knowledge (applies throughout, not tied to one feature)
- **Python fundamentals**: type hints, async/await, project structuring, virtual environments, dependency management (pip/requirements or a tool like Poetry)
- **REST API design conventions**: proper use of HTTP methods/status codes, consistent URL/resource naming
- **Git/GitHub**: branching, commits, pull requests (if you want to simulate real team workflow even solo)
- **Postman** (or an alternative like Insomnia/HTTPie): manually testing endpoints as you build, before automated tests exist
- **General debugging skills**: reading FastAPI/SQLAlchemy tracebacks, inspecting SQL being generated, using logging effectively

If it'd help, I can later turn this into a checklist/tracker format (e.g., a markdown file or simple board) so you can tick off features as you build — just say the word when you're ready for that.