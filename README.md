[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/SO1PVZ3b)
# Neurosynth Backend

A lightweight Flask backend that exposes **functional dissociation** endpoints on top of a Neurosynth-backend PostgreSQL database.

The service provides two APIs that return studies mentioning one concept/coordinate **but not** the other (A \ B). You can also query the opposite direction (B \ A).

Check out the app on https://bloggermandolin.com/neurosynth/

(Also welcome to surf my blog: https://bloggermandolin.com)

---

## Table of Contents

- [Endpoints](#endpoints)
  - [Dissociate by terms](#dissociate-by-terms)
  - [Dissociate by MNI coordinates](#dissociate-by-mni-coordinates)
- [Quick Start](#quick-start)
  - [1) Provision PostgreSQL](#1-provision-postgresql)
  - [2) Verify the connection](#2-verify-the-connection)
  - [3) Populate the database](#3-populate-the-database)
  - [4) Run the Flask service](#4-run-the-flask-service)
  - [5) Smoke tests](#5-smoke-tests)
- [Environment Variables](#environment-variables)
- [Example Requests](#example-requests)
- [Requirements](#requirements)
- [Notes](#notes)
- [Deployment: gunicorn + systemd (production)](#deployment-gunicorn-systemd-production)
- [License](#license)

---

## Endpoints

### Dissociate by terms

```
GET /dissociate/terms/<term_a>/<term_b>
```

Returns studies that mention **`term_a`** but **not** `term_b`.

**Examples**

```
/dissociate/terms/posterior_cingulate/ventromedial_prefrontal
/dissociate/terms/ventromedial_prefrontal/posterior_cingulate
```

---

### Dissociate by MNI coordinates

```
GET /dissociate/locations/<x1_y1_z1>/<x2_y2_z2>
```

Coordinates are passed as `x_y_z` (underscores, not commas).  
Returns studies that mention **`[x1, y1, z1]`** but **not** `[x2, y2, z2]`.

**Default Mode Network test case**

```
/dissociate/locations/0_-52_26/-2_50_-6
/dissociate/locations/-2_50_-6/0_-52_26
```

> Tip: You may design a single endpoint that returns **both directions** in one response (A–B **and** B–A) if that better suits your client.

---

## Quick Start

### 1) Provision PostgreSQL

Create a PostgreSQL database (e.g., on Render).

### 2) Verify the connection

```bash
python check_db.py --url "postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DBNAME>"
```

### 3) Populate the database

```bash
python create_db.py --url "postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DBNAME>"
```

### 4) Run the Flask service

Deploy `app.py` as a Web Service (e.g., on Render) and set the environment variable:

- `DB_URL=postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DBNAME>`

Use a production server such as Gunicorn as your start command:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

### 5) Smoke tests

After deployment, check the basic endpoints:

- Images: `https://<your-app>.onrender.com/img`
- DB connectivity: `https://<your-app>.onrender.com/test_db`

---

## Environment Variables

- **`DB_URL`** – Full PostgreSQL connection string used by the app.  
  Example: `postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DBNAME>`

> **Security note:** Never commit real credentials to version control. Use environment variables or your hosting provider’s secret manager.

---

## Example Requests

**By terms**

```bash
curl https://<your-app>.onrender.com/dissociate/terms/posterior_cingulate/ventromedial_prefrontal
curl https://<your-app>.onrender.com/dissociate/terms/ventromedial_prefrontal/posterior_cingulate
```

**By coordinates**

```bash
curl https://<your-app>.onrender.com/dissociate/locations/0_-52_26/-2_50_-6
curl https://<your-app>.onrender.com/dissociate/locations/-2_50_-6/0_-52_26
```

---

## Requirements

- Python 3.10+
- PostgreSQL 12+
- Python dependencies (typical):
  - `Flask`
  - `SQLAlchemy`
  - PostgreSQL driver (e.g., `psycopg2-binary`)
  - Production WSGI server (e.g., `gunicorn`)

---

## Notes

- Path parameters use underscores (`_`) between coordinates: `x_y_z`.
- Term strings should be URL-safe (e.g., `posterior_cingulate`, `ventromedial_prefrontal`). Replace spaces with underscores on the client if needed.
- The term/coordinate pairs above illustrate a **Default Mode Network** dissociation example. Adjust for your analysis.

---

## Deployment: gunicorn + systemd (production)

<a name="deployment-gunicorn-systemd-production"></a>

The following is a concise, copy-paste friendly guide to run this Flask app in production using Gunicorn managed by systemd. Replace placeholders (USER, PROJECT_DIR, VENV_GUNICORN, DB_URL) with values matching your server.

1) Prerequisites

- System user that will run the service (e.g. `flaskuser`).
- A Python virtual environment with your app dependencies installed and `gunicorn` available.
- Root access to create systemd unit and environment files.

2) Create an environment file (keeps secrets out of the unit)

Create `/etc/default/neurosynth` (owner root, mode 600) with at least:

```
# /etc/default/neurosynth
DB_URL='postgresql://<readonly_user>:<StrongPassword>@127.0.0.1:5432/neurosynth'
# Optionally add FLASK_ENV=production or other env vars
```

- readonly_user: Your database user
- StrongPassword: Your database user password

3) Create a run directory for the Gunicorn PID

```
sudo mkdir -p /run/gunicorn
sudo chown USER:USER /run/gunicorn
```

While you are hardening the deployment, ensure the environment file remains private:

```
sudo chmod 600 /etc/default/neurosynth
sudo chown root:root /etc/default/neurosynth
```

USER: System user that will run the service (e.g. `flaskuser`)

4) Create the systemd unit

Create `/etc/systemd/system/neurosynth.service` with the following content (replace USER, PROJECT_DIR, and the virtualenv gunicorn path):

```
[Unit]
Description=Gunicorn service for neurosynth Flask app
After=network.target

[Service]
Type=simple
User=USER
Group=USER
WorkingDirectory=PROJECT_DIR
EnvironmentFile=/etc/default/neurosynth
ExecStart=VENV_GUNICORN \
  --workers 1 --worker-class gthread --threads 2 \
  --bind 127.0.0.1:8000 \
  --timeout 30 \
  --max-requests 1000 --max-requests-jitter 50 \
  --access-logfile - --error-logfile - \
  --pid /run/gunicorn/neurosynth.pid \
  app:app
PIDFile=/run/gunicorn/neurosynth.pid
Restart=always
RestartSec=5
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
```

Notes:
- Use `VENV_GUNICORN` like `/home/flaskuser/neurosynth-env/bin/gunicorn`.
- Keep `WorkingDirectory` set to your project root where `app.py` lives.

After reboot

If you enabled the unit with `systemctl enable`, systemd will start it at boot. To verify or (re)start after a reboot run:

```bash
sudo systemctl status neurosynth.service -l
# if not running, start it
sudo systemctl start neurosynth.service
```

5) Enable and start the service

```
sudo systemctl daemon-reload
sudo systemctl enable --now neurosynth.service
sudo systemctl status neurosynth.service -l
```

6) Logs and common management

- Follow logs:

```
sudo journalctl -u neurosynth.service -f
```

- Graceful reload (deploy new code):

```
sudo systemctl reload neurosynth.service
```

- Restart or stop:

```
sudo systemctl restart neurosynth.service
sudo systemctl stop neurosynth.service
```

7) Quick smoke tests

- Directly talk to Gunicorn (bypass nginx):

```
curl -v http://127.0.0.1:8000/test_db
```

- Through nginx (if configured to proxy `/neurosynth/`):

```
curl -v https://yourdomain.example/neurosynth/test_db
```

8) Security and production tips

- Run Gunicorn on `127.0.0.1` and let nginx handle TLS and external exposure.
- Do not store real credentials inside the repository. Use `/etc/default/neurosynth` or a secret manager.
- Consider resource limits (MemoryMax) in the unit or a process supervisor if you run on low-RAM instances.
- Use a monitoring/healthcheck service to alert on failures and CPU/memory pressure.

If you'd like, I can provide a filled-in unit file tailored to your environment (with concrete `User`, `PROJECT_DIR`, and `VENV_GUNICORN`).

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
