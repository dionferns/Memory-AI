# Recall — AI-Assisted Spaced Repetition Knowledge System

Recall is a personal knowledge management app that combines AI-generated flashcards with spaced repetition scheduling (FSRS). You organize notes into folders, an AI agent proposes flashcards from your notes, you review and approve them, and the system schedules when each card should come back for review based on how well you remembered it.

This project is being built alongside a full-stack Python API development course, using the course's software engineering curriculum (FastAPI, PostgreSQL, SQLAlchemy, JWT auth, testing, CI/CD, Docker, deployment) as the backend foundation, with an AI agent layer (LangChain/LangGraph) added on top for the flashcard-generation feature.

---

## Project Goals

- Build production-grade software engineering fundamentals: REST API design, relational database modeling, authentication, automated testing, CI/CD, and deployment
- Apply those fundamentals to a real, personally useful AI-powered application rather than a toy project
- Practice integrating an AI agent into a traditional backend system (not just building agent pipelines in isolation)

---

## Phase 1 — Core Personal App

- **Auth**: user registration, login, JWT-based authentication, protected routes
- **Folders**: create, nest, rename, delete; organize notes by subject
- **Notes**: create/edit/delete notes within folders (text now; PDF/URL ingestion later)
- **AI flashcard generation**: agent reads a note and proposes flashcards in a pending state
- **Card review workflow**: approve, edit, or reject AI-proposed cards before they go live
- **Spaced repetition (FSRS)**: track per-card memory state (stability, difficulty, due date) and reschedule after each review
- **Due-cards queries**: fetch cards due today, filterable by folder
- **Weekly cross-subject recall routine**: pull a balanced batch of due cards across all subjects to build a consistent review habit
- **Likes**: mark favorite/important cards
- **Testing**: pytest suite covering CRUD, auth, FSRS logic, and a mocked AI generation call
- **CI/CD**: GitHub Actions pipeline — install, spin up test DB, run tests, build image
- **Containerization**: Dockerfile + Docker Compose (API + Postgres)
- **Deployment**: three paths — Heroku, Docker Compose, and a raw Ubuntu VM (Nginx, systemd, SSL, firewall)

## Phase 2 — Community Layer

- **Public folders**: mark a folder shareable
- **Browse & clone**: view other users' public decks and clone them into your own account
- **Voting**: upvote/downvote public decks
- **Following**: follow other users whose decks you like
- **Public feed**: sorted/filterable feed of public decks (by popularity, by followed users)

---

## Tech Stack

- **Backend**: FastAPI, Pydantic
- **Database**: PostgreSQL, SQLAlchemy ORM, Alembic migrations
- **Auth**: JWT, OAuth2 password flow
- **AI**: LangChain / LangGraph (LLM provider TBD)
- **Testing**: pytest
- **CI/CD**: GitHub Actions
- **Containerization**: Docker, Docker Compose
- **Deployment**: Heroku, Docker Compose, Ubuntu VM (Nginx, Gunicorn, systemd)

---

## Status

🚧 In development — following course structure, building alongside course videos.

## Course Reference

This project's software engineering foundation follows Sanjeev Thiyagarajan's *"Learn Python API Development"* course (FastAPI, PostgreSQL, SQLAlchemy, JWT, testing, CI/CD, Docker, deployment), adapted from the course's example project to this app's schema and features.