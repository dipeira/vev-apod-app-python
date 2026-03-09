# Running with Docker

The application ships with a `Dockerfile`, `docker-compose.yml`, and `nginx.conf` for a production-ready containerised deployment.

## Architecture

```
Internet → nginx (host:8085 → container:80) → Gunicorn (port 5000, internal)
                                    |
                          Flask application
                                    |
                    SQLite (app_instance volume)
                    File data (app_data volume)
```

- **nginx** listens on container port 80 (mapped from host port 8085), proxies all requests to the Flask/Gunicorn container
- **Gunicorn** runs 2 workers with a 600-second timeout (accommodates long LibreOffice conversions)
- **Two Docker volumes** persist data across container restarts: `app_data` and `app_instance`

---

## Prerequisites

- Docker Engine 20.10+
- Docker Compose v2 (`docker compose` command)

---

## Step 1 — Configure Environment

```bash
cd vev-apod-python
cp .env.example .env
```

Edit `.env`:

```env
SECRET_KEY=your-long-random-secret-key-here
ORG_NAME=Διεύθυνση Π.Ε. Ηρακλείου
```

> **Important**: Always set a strong `SECRET_KEY` in production. The default is insecure.

---

## Step 2 — Build and Start

```bash
docker compose up -d --build
```

- `--build` — rebuilds the image (required on first run and after any code change)
- `-d` — runs in the background (detached mode)

The first build downloads the base image and installs LibreOffice, which takes several minutes.

---

## Step 3 — Verify

```bash
docker compose ps
```

Both `web` and `nginx` services should show `running`.

Open `http://<server-ip>:8085` in your browser.

---

## Common Commands

### View logs

```bash
# All services
docker compose logs -f

# Web application only
docker compose logs -f web

# nginx only
docker compose logs -f nginx
```

### Stop containers

```bash
docker compose down
```

> This stops and removes containers but **preserves volumes** (your data is safe).

### Stop and remove all data (destructive)

```bash
docker compose down -v
```

> **Warning**: `-v` removes the Docker volumes. All uploaded files and the database will be deleted permanently.

### Restart containers

```bash
docker compose restart
```

### Restart after code changes

```bash
docker compose up -d --build
```

### Open a shell inside the web container

```bash
docker compose exec web bash
```

---

## Port Configuration

The application listens on port **8085** externally. This is set in `docker-compose.yml`:

```yaml
ports:
  - "8085:80"
```

To change the external port, edit the left side of the mapping:

```yaml
ports:
  - "80:80"    # expose on port 80 instead
```

---

## Volume Locations

Docker named volumes are managed by Docker. To find the actual path on the host:

```bash
docker volume inspect vev-apod-python_app_data
docker volume inspect vev-apod-python_app_instance
```

---

## Updating the Application

```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose up -d --build
```

The `init_db.py` script runs automatically on every container start (it is idempotent — safe to run repeatedly).

---

## Default Credentials

| Username | Password | Role |
|---|---|---|
| admin | d1pe1712 | Administrator |

Change the admin password via the Users management page after first login.
