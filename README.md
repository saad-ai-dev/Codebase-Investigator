# 🕵️ Codebase Investigator

Codebase Investigator is a Python application for investigating public GitHub repositories through plain-English questions. A user pastes a repo URL, asks something like "How does auth work here?" or "What code is safe to delete?", and the app returns an answer grounded in specific files and line ranges.

It also produces a separate audit for each non-trivial answer so a human reviewer can judge whether the result is actually trustworthy.

## WHAT IT IS

This project is a small product, not just a script.

It includes:

- a Python engine that clones and inspects public GitHub repositories
- a browser-based UI for multi-turn investigation
- a CLI for direct terminal usage
- a programmatic verifier for citation integrity
- a separate model pass for auditing answer quality
- local developer tooling, Git hooks, CI workflows, and Docker support

The stack is intentionally Python-first. The frontend is plain static HTML, CSS, and JavaScript served directly by the Python app. There is no Node build pipeline in this repository.

## PURPOSE

This project was built for an interview prompt with three real requirements:

1. Answer questions about a codebase in plain English.
2. Ground those answers in specific files and line ranges.
3. Provide an audit path that is independent from the answer generation step.

The project is designed to satisfy those requirements directly.

It is also built to stay coherent over follow-up questioning. A user can ask a second or third question, challenge a previous answer, or redirect the investigation to a different part of the repo without losing the earlier trail.

## HOW IT WORKS

For each repository session, the app follows this flow:

1. Clone the public GitHub repository locally.
2. Build a lightweight representation of source files and symbols.
3. Retrieve likely relevant snippets for the user question.
4. Send those snippets plus prior conversation context to the answering model.
5. Validate whether the cited snippet references are structurally valid.
6. Run a second, separate audit pass against the answer, evidence, and verifier result.
7. Persist the session so future turns can build on the previous ones.

This creates three distinct trust signals:

- the answer itself
- the programmatic verifier result
- the independent audit result

## ARCHITECTURE

The application is split into a few clear parts.

The source tree is intentionally flat. The Python modules live directly under `src/`, and the browser assets live under `src/static/`.

### Core backend

- [engine.py](src/engine.py)
  Coordinates retrieval, answer generation, verification, auditing, and session updates.
- [repository.py](src/repository.py)
  Handles repository cloning, file indexing, and snippet retrieval.
- [audit.py](src/audit.py)
  Performs programmatic checks on snippet references and evidence integrity.
- [prompts.py](src/prompts.py)
  Defines the structured prompts and schemas for the answer pass and the separate audit pass.
- [session.py](src/session.py)
  Stores and reloads multi-turn repository sessions.
- [openai_client.py](src/openai_client.py)
  Wraps the OpenAI Responses API calls used by the engine.

### Web application

- [webapp.py](src/webapp.py)
  Runs the HTTP server and exposes the JSON API used by the browser client.
- [index.html](src/static/index.html)
  Main browser interface.
- [app.css](src/static/app.css)
  Styling for the UI.
- [app.js](src/static/app.js)
  Frontend behavior and API interaction.

### Storage

Sessions are persisted on disk. Each session stores:

- the repository URL
- the local clone path
- prior turns
- retrieved snippets
- the generated answer
- the verifier result
- the audit result

Default session location:

```text
.investigator/sessions
```

## SETUP

You can run the project locally with Python, or through Docker.

### Prerequisites

For local development:

- Python 3.10 or newer
- `git`
- an `OPENAI_API_KEY`

Optional but useful:

- `make`
- `pre-commit`

For Docker:

- Docker 24 or newer
- Docker Compose v2
- an `OPENAI_API_KEY`

### Environment variables

The application uses these environment variables:

- `OPENAI_API_KEY`
  Required. Used for answer generation and the audit pass.
- `OPENAI_MODEL`
  Optional. Default: `gpt-5.5`
- `OPENAI_AUDIT_MODEL`
  Optional. Default: `gpt-5.4-mini`
- `SESSION_ROOT`
  Optional. Default value: `.investigator/sessions`
- `HOST_PORT`
  Optional for Docker Compose. Default: `8000`

An example environment file is provided in [.env.example](.env.example).

For local CLI and web runs, the app will automatically read `.env` from the repo root if it exists. Shell environment variables still take precedence over values from the file.

Use a local-safe `SESSION_ROOT` such as `.investigator/sessions`. Do not point local runs at `/app/...` unless you are actually inside the Docker container.

### Local installation

Install the package and development dependencies:

```bash
python3 -m pip install -e .[dev]
```

Create a local environment file:

```bash
cp .env.example .env
```

Set the required API key in `.env`:

```text
OPENAI_API_KEY=your_key_here
```

You can still export variables in the shell if you want them to override `.env`:

```bash
export OPENAI_API_KEY=your_key_here
```

Optional model overrides:

```bash
export OPENAI_MODEL=gpt-5.5
export OPENAI_AUDIT_MODEL=gpt-5.4-mini
```

## RUNNING THE PROJECT

### Web UI

Start the local server:

```bash
codebase-investigator serve --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

### Single question from the terminal

```bash
codebase-investigator ask https://github.com/owner/repo "How does auth work here?"
```

### Interactive terminal mode

```bash
codebase-investigator chat https://github.com/owner/repo
```

### Makefile shortcuts

The repo includes a [Makefile](Makefile) with common commands:

```bash
make install
make install-dev
make serve
make test
make lint
make format
make check
make hooks
make precommit
make docker-build
make docker-up
make docker-down
```

## DOCKER

Container-related files:

- [Dockerfile](Dockerfile)
- [docker-compose.yml](docker-compose.yml)
- [docker/entrypoint.sh](docker/entrypoint.sh)
- [.dockerignore](.dockerignore)
- [.env.example](.env.example)

### Start with Docker Compose

Copy the example environment file:

```bash
cp .env.example .env
```

Set at least:

```text
OPENAI_API_KEY=your_key_here
```

Then start the app:

```bash
docker compose up --build
```

Open:

```text
http://127.0.0.1:8000
```

If you changed `HOST_PORT`, use that port instead.

### Detached mode

```bash
docker compose up --build -d
```

### Stop the stack

```bash
docker compose down
```

### Remove the persisted Docker volume

```bash
docker compose down -v
```

### Build and run the image directly

```bash
docker build -t codebase-investigator:local .
```

```bash
docker run --rm \
  -p 8000:8000 \
  -e OPENAI_API_KEY=your_key_here \
  -e OPENAI_MODEL=gpt-5.5 \
  -e OPENAI_AUDIT_MODEL=gpt-5.4-mini \
  -v codebase-investigator-sessions:/app/.investigator \
  codebase-investigator:local
```

Docker Compose persists session data through a named volume so repo clones and conversation history survive container restarts.

## EC2 DEPLOYMENT

For a simple EC2 deployment, this repository includes [deploy.sh](deploy.sh).

The script is designed for the exact case where you want the app:

- running on an EC2 instance
- listening on port `5600`
- running in the background
- restartable without manually killing old processes

### What `deploy.sh` does

It will:

- create a local virtual environment if one does not already exist
- install the application into that environment
- load variables from `.env` if present
- stop the previous background process if one is already running
- start the app on `0.0.0.0:5600` with `nohup`
- write logs to `logs/codebase-investigator.log`
- store the PID in `.run/codebase-investigator.pid`

### EC2 prerequisites

- Python 3.10 or newer installed on the instance
- `git` installed on the instance
- this repository cloned onto the instance
- `OPENAI_API_KEY` set in `.env` or in the shell
- the EC2 security group must allow inbound TCP traffic on port `5600`

### Start on EC2

Create the environment file if needed:

```bash
cp .env.example .env
```

Set at minimum:

```text
OPENAI_API_KEY=your_key_here
```

Then deploy:

```bash
./deploy.sh
```

Open:

```text
http://your-ec2-public-ip:5600
```

### Useful EC2 commands

Check status:

```bash
./deploy.sh status
```

View logs:

```bash
./deploy.sh logs
```

Restart:

```bash
./deploy.sh restart
```

Stop:

```bash
./deploy.sh stop
```

### EC2 notes

- The script defaults to port `5600`.
- You can override the port with `PORT=...` if needed.
- You can override the bind host with `HOST=...` if needed.
- For a production-facing deployment, you would usually put Nginx or another reverse proxy in front of the app.

## DEVELOPMENT WORKFLOW

This repository uses Python-native tooling.

### Linting and formatting

- `ruff` is used for linting and formatting
- configuration lives in [pyproject.toml](pyproject.toml)

Useful commands:

```bash
make lint
make format
make check
```

### Git hooks

Git hooks are managed with [pre-commit](.pre-commit-config.yaml).

Install hooks:

```bash
make hooks
```

Run hooks manually:

```bash
make precommit
```

The hook set includes:

- Python linting and formatting checks
- file hygiene checks
- Python bytecode compilation
- unit tests
- Docker build validation when Docker is available

### Tests

Run the test suite with:

```bash
make test
```

or:

```bash
python3 -m unittest discover -s tests
```

The current tests cover:

- GitHub URL parsing
- answer verifier behavior
- session persistence
- web serialization

## CI / WORKFLOWS

The repository uses three separate GitHub Actions workflows:

- [lint.yml](.github/workflows/lint.yml)
- [tests.yml](.github/workflows/tests.yml)
- [docker.yml](.github/workflows/docker.yml)

### Lint workflow

Runs:

- Python setup
- development dependency installation
- `pre-commit run --all-files`

### Tests workflow

Runs:

- unit tests on Python 3.10
- unit tests on Python 3.11

### Docker workflow

Runs:

- Docker image build
- container startup with a dummy API key
- healthcheck verification against `/api/health`

## API

The built-in web server exposes:

- `GET /api/health`
- `POST /api/session`
- `GET /api/session/:session_id`
- `POST /api/ask`

The browser client talks directly to this server. There is no separate frontend build service.

## SECURITY NOTES

- Never expose `OPENAI_API_KEY` in client-side JavaScript.
- Rotate any API key that has been pasted into chat, logs, or screenshots.
- Treat cloned repositories as untrusted input. This app reads repository files locally but does not execute repository code.
- GitHub Pages alone is not sufficient for hosting this app because the OpenAI key must remain server-side.

## LIMITATIONS

- Retrieval is lexical and symbol-based, not embedding-based.
- Large repositories are intentionally size-limited during indexing.
- GitHub URLs with branch names that contain `/` are handled conservatively.
- The built-in server is suitable for interview and demo use, not production traffic.
- The Docker image is a straightforward runtime container, not a production deployment system.
