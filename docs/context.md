## Learning Approach

I'm learning backend software engineering by following Sanjeev Thiyagarajan's 
"Learn Python API Development" course, and applying every concept directly to 
my own project (Recall) instead of the course's example app. I watch each 
section, then build the equivalent feature in Recall using my own schema.

## Course Content Covered

- **FastAPI basics**: routes, path operations, Pydantic schemas/validation
- **PostgreSQL + raw SQL**: WHERE, LIKE, ORDER BY, LIMIT/OFFSET, joins
- **SQLAlchemy ORM**: models, relationships, foreign keys, CRUD
- **Auth**: password hashing, JWT, OAuth2 login flow, protected routes, 
  owner-only edit/delete
- **Alembic**: database migrations
- **Environment variables & CORS**
- **Votes/relationships pattern**: many-to-many tables, joined queries
- **Testing**: pytest, fixtures, parametrize, TestClient, test database
- **CI/CD**: GitHub Actions, secrets, automated test + build pipeline
- **Docker**: Dockerfile, Docker Compose, Docker Hub
- **Deployment**: Heroku, Docker Compose, and raw Ubuntu VM 
  (Postgres, Gunicorn, systemd, Nginx, SSL, firewall)

Each concept above maps to a specific feature in Recall — see the feature 
list for details.