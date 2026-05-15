# Task Completion Plan: Fix Docker Compose Container Conflict

## [ ] Step 1: Edit docker-compose.yml
- Remove obsolete `version: "3.9"` line to eliminate warning.

## [ ] Step 2: Stop and clean up existing containers
- Run `docker compose down` to remove conflicting ollama container and others.

## [ ] Step 3: Start services fresh
- Run `docker compose up --build -d`.

## [ ] Step 4: Verify
- Run `docker compose ps` to confirm all services are Up/healthy.
- Test API health at http://localhost:8000/health.

