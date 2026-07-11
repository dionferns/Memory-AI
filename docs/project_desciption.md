# Recall — Full Project Description & Course Mapping

## What the project is

**Recall** is a personal AI-assisted spaced repetition system — essentially "AI-powered Anki." You organize notes into folders, an AI reads your notes and proposes flashcards, you approve/edit/reject them, and the app schedules when you should review each card using the FSRS spaced repetition algorithm. On top of that, there's a habit-formation layer (weekly cross-subject recall sessions) and, in Phase 2, a community layer where you can share decks publicly and interact with other users' content the way you would on a social app.

The whole point of this project is that it's *not* just an AI app — it's a full backend software engineering project (auth, database design, migrations, testing, CI/CD, deployment) that happens to have an AI feature at its core, so you get both skillsets from one build.

---

## Phase 1 — Core Personal App

### 1. User accounts & authentication
You register and log in; every folder, note, and card belongs to you and only you.
**Course match:** the entire auth block — user registration and password hashing, JWT token creation, login flow with OAuth2PasswordRequestForm, protecting routes, and verifying who's currently logged in.

### 2. Folders (with nesting)
You create folders to organize subjects (e.g., "Machine Learning" → "Transformers" as a sub-folder). Folders belong to a user.
**Course match:** basic path operations and CRUD (create/read/update/delete), plus the "self-referential relationship" pattern — a folder pointing to a parent folder is conceptually the same as any foreign-key relationship taught in the course, just applied to itself instead of another table.

### 3. Notes
Inside a folder, you add notes — raw text, pasted content, or content extracted from a source like a PDF or URL. Notes are the raw material the AI reads from.
**Course match:** more CRUD + Pydantic schema validation (making sure a note has required fields, correct types, reasonable length limits, etc.), and response models (deciding what part of a note gets returned in an API response vs. hidden).

### 4. AI-generated flashcards (your AI engineering piece — not covered by the course)
You trigger card generation on a note. An AI agent reads the note and proposes a batch of flashcards (question/answer pairs). These land in a "pending" state — they are not live yet.
**Not in the course** — this is where your LangChain/LangGraph experience comes in. This is the one part of the project you said you'd build using AI, since it's outside the software engineering skill the course teaches.

### 5. Card review & editing workflow
You look at AI-proposed cards and approve, edit, or reject each one before it becomes part of your real deck.
**Course match:** this is standard "update" and "delete only your own resource" logic — the exact pattern the course teaches when it restricts editing/deleting posts to their owner.

### 6. Spaced repetition scheduling (FSRS)
Every time you review a card and rate how well you remembered it, the system recalculates when you should see that card again, tracking things like stability and difficulty of memory for that card.
**Not in the course** — this is a self-contained algorithm you'll write and test independently. It naturally becomes one of the richest places to practice automated testing (see below) because it has clear, checkable inputs/outputs.

### 7. Due-cards queries
You can ask "what cards are due today," filtered by folder or across everything.
**Course match:** SQL fundamentals — `WHERE`, `LIKE`, ordering results, `LIMIT`/`OFFSET` — plus later, joining multiple tables together (your cards, your scheduling data, your folders) into one query, and using query parameters to filter/sort results through the API.

### 8. Weekly cross-subject recall routine
Once a week (or on demand), the app pulls a batch of due cards spanning *all* your subjects, not just one folder, to build the "do a little recall from everything" habit you described.
**Course match:** same joins/query-parameter skills as above, just applied at a broader scope — a good stretch exercise for combining filtering + sorting + limiting results meaningfully.

### 9. "Like" a card
You can mark certain cards as favorites — maybe ones you find especially useful or tricky.
**Course match:** the votes table pattern — a simple table linking a user to a card they've acted on. In the course this powers upvotes/downvotes on posts; here it's a lighter personal version of the same relationship structure.

### 10. Database schema evolution
As you build, you'll add new tables incrementally (the scheduling table comes after cards already exist, for example).
**Course match:** database migrations — adding structured, trackable changes to your schema over time instead of just editing tables by hand.

### 11. Environment variables & configuration
Database credentials, JWT secret, and your LLM API key all need to be handled securely rather than hardcoded.
**Course match:** the environment variables section, directly.

### 12. CORS
If you ever build any kind of frontend (even a simple one) that talks to this API from a browser, you'll hit this.
**Course match:** the CORS section, directly.

### 13. Automated testing
Testing covers: the FSRS scheduling math with many different input combinations, the CRUD endpoints, the auth flow, and the AI card-generation endpoint — but for that last one, using a fake/mocked AI response instead of actually calling a real model during tests (so tests are fast, free, and repeatable).
**Course match:** the entire pytest section — fixtures, parametrized tests, testing exceptions, a dedicated test database that gets created and destroyed per test run, and using FastAPI's test client.

### 14. CI/CD pipeline
Every time you push code, a pipeline automatically installs dependencies, spins up a test database, runs your full test suite, and builds a Docker image — failing loudly if anything breaks.
**Course match:** the GitHub Actions section end-to-end, including handling secrets (like your database password and LLM API key) safely in CI.

### 15. Containerization
The whole app gets packaged so it runs identically regardless of machine — one container for the API, one for Postgres, connected together.
**Course match:** Dockerfile, Docker Compose, bind mounts, and pushing images to Docker Hub.

### 16. Deployment (three separate ways, for full practice)
- **Heroku** — fastest path to a live version.
- **Docker Compose** — running the containerized version anywhere, dev/prod parity.
- **Raw Ubuntu VM** — the "real" production path: installing Postgres yourself, running the app as a background service via systemd, putting Nginx in front of it, setting up a domain name and SSL, and configuring a firewall.

**Course match:** all three deployment sections of the course, applied to your actual app instead of the course's toy project.

---

## Phase 2 — Community Layer (closes the one gap Phase 1 has)

Phase 1 is inherently personal/single-user in spirit, so it doesn't naturally exercise the course's *social* patterns (interacting with other users' data). Phase 2 adds that back in a way that still fits an Anki-like app naturally — real Anki has a public shared-deck repository, so this isn't a stretch.

### 17. Public/shareable folders
You can mark a folder as public, making its notes and cards visible to other users.

### 18. Browsing & cloning shared decks
Other users can browse public folders and copy ("clone") one into their own account to start reviewing it themselves.

### 19. Upvoting/downvoting shared decks
Users can vote on public folders they find useful, the same way people vote on posts in a typical social app.

### 20. Following other users
You can follow specific people whose decks you like, so you can filter the public feed down to just the creators you care about.

### 21. Sorted/filterable public feed
A feed of public decks that can be sorted by popularity (vote count) and optionally filtered to only show decks from people you follow.

**Course match for all of Phase 2:** this is the most direct 1:1 mapping in the entire project to the course's core social-app pattern — the votes table, the relationship between users, and the joined query that pulls a post together with its owner's info and its vote count, filtered and sorted by parameters. Phase 1 only *touches* this pattern lightly (via "likes"); Phase 2 is where you actually build it the way the course does.

---

## Summary: What's course-covered vs. what's genuinely new

**Fully course-covered (software engineering skills):**
Auth/JWT, CRUD operations, Pydantic validation, response models, SQL fundamentals, SQLAlchemy ORM, database relationships and foreign keys, joins, query parameters, database migrations, environment variables, CORS, votes-style tables, follows-style relationships, testing with pytest (fixtures, parametrize, test client, test database), CI/CD with GitHub Actions, Docker/Docker Compose, and all three deployment paths.

**Not covered by the course (your own build, mostly AI engineering):**
- The AI agent that reads notes and proposes flashcards
- The FSRS spaced repetition scheduling algorithm itself
- The weekly cross-subject recall selection logic
- The clone-a-public-deck feature (a transactional "copy" operation, a bit beyond basic CRUD)
- Any frontend/UI, which the course doesn't build at all (it stays API-only with Postman)

This gives you close to full coverage of the course content while building something you'll actually use, plus a clean line between "this part I'm doing purely for software engineering practice" and "this part is where my existing AI engineering skill shows up."