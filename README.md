# Messenger Archive

A self-hosted system to archive Facebook Messenger group chats in real-time, with a web interface for browsing, searching, and organizing conversations.

## Architecture

```
Messenger <--> mautrix-meta (bridge) <--> Synapse (Matrix) <--> Archive Service
                                                |
                                           PostgreSQL
                                                |
                                         FastAPI Backend
                                                |
                                        Next.js Frontend
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| web | 3000 | Next.js frontend |
| api | 8000 | FastAPI backend |
| synapse | 8008 | Matrix homeserver |
| element | 8080 | Matrix web client |
| postgres | 5432 | Database |
| mautrix-meta | 29319 | Messenger bridge |
| archive-service | - | Message archiver |

## Deployment

### Prerequisites

- Docker and Docker Compose
- A Facebook/Messenger account
- (Optional) A server for remote deployment (e.g., Oracle Cloud Free Tier)

### Step 1: Clone and Configure

```bash
git clone <repo-url>
cd messenger-archive
```

Create a `.env` file:

```bash
# Database
POSTGRES_USER=archive
POSTGRES_PASSWORD=archivepass123
POSTGRES_DB=messenger_archive
DATABASE_URL=postgresql://archive:archivepass123@postgres:5432/messenger_archive

# Matrix
MATRIX_HOMESERVER_URL=http://synapse:8008
MATRIX_HOMESERVER_DOMAIN=archive.local

# Auth (generate your own password hash - see below)
ARCHIVE_PASSWORD_HASH=$2b$12$your_hash_here
SESSION_SECRET=$(openssl rand -hex 32)

# API
API_HOST=0.0.0.0
API_PORT=8000
API_URL=http://api:8000
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Generate a password hash for the web UI:

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'your-password-here', bcrypt.gensalt()).decode())"
```

### Step 2: Start Services

```bash
docker compose up -d
```

Wait for all services to start (check with `docker compose ps`).

### Step 3: Create Matrix Users

Create an admin user for yourself:

```bash
docker exec archive-synapse register_new_matrix_user \
  -c /data/homeserver.yaml \
  -u admin \
  -p your-password \
  --no-admin
```

The archive service user is created automatically with credentials from the config.

### Step 4: Login to Element

1. Open http://localhost:8080 (Element web client)
2. Sign in with:
   - Username: `admin`
   - Password: `your-password`
   - Homeserver: `http://localhost:8008`

### Step 5: Connect Messenger

1. In Element, start a new chat with `@metabot:archive.local`
2. Send `help` to see available commands
3. Send `login` to start authentication
4. Follow the prompts to paste your Messenger cookies:

**To get cookies:**
1. Open https://www.messenger.com in your browser
2. Log in to Messenger
3. Open Developer Tools (F12) -> Network tab
4. Refresh the page
5. Right-click any request to messenger.com -> Copy -> Copy as cURL
6. Paste the entire cURL command to the bot

### Step 6: Configure Room Archiving

By default, the archive service only archives messages from rooms matching the `ARCHIVE_ROOM_FILTER` environment variable in `docker-compose.yml`.

To change which room to archive:

1. Edit `docker-compose.yml`
2. Update `ARCHIVE_ROOM_FILTER` to match your room name (partial match, case-insensitive)
3. Restart: `docker compose restart archive-service`

**Important:** The archive service user (`@archive:archive.local`) must be invited to the room to receive messages. Once your Messenger group appears in Element, invite `@archive:archive.local` to that room.

### Step 7: Access the Web UI

1. Open http://localhost:3000
2. Log in with the password you set in `ARCHIVE_PASSWORD_HASH`
3. View archived messages in the Messages or Database pages

## Backfilling Old Messages

By default, backfill is enabled. The bridge will fetch:
- Up to 500 messages when first syncing a room
- Up to 1000 missed messages after restarts

To adjust these limits, edit `config/mautrix-meta/config.yaml`:

```yaml
backfill:
    enabled: true
    max_initial_messages: 500
    max_catchup_messages: 1000
```

Then restart: `docker compose restart mautrix-meta`

## Production Deployment (AWS)

The project includes a `deploy.sh` script for deploying to AWS EC2.

### First-Time Setup

```bash
# 1. Deploy AWS infrastructure (EC2, S3)
./deploy.sh infra

# 2. Point your DuckDNS domain to the Elastic IP shown in output

# 3. Setup .env on server
./deploy.sh migrate:env
ssh ubuntu@<server-ip> nano /opt/messenger-archive/.env

# 4. Run full migration (db, users, bridge credentials, media, room access)
./deploy.sh migrate

# 5. Deploy application
./deploy.sh app
```

### Deploy Commands

| Command | Description |
|---------|-------------|
| `./deploy.sh app` | Deploy all services (full rebuild) |
| `./deploy.sh web` | Deploy frontend only (Next.js) |
| `./deploy.sh api` | Deploy backend only (FastAPI) |
| `./deploy.sh archive` | Deploy archive-service only |

### Migration Commands

| Command | Description |
|---------|-------------|
| `./deploy.sh migrate` | Full migration (interactive) |
| `./deploy.sh migrate:db` | Migrate messenger_archive database |
| `./deploy.sh migrate:bridge` | Migrate Facebook login credentials |
| `./deploy.sh migrate:media` | Sync Synapse media store |
| `./deploy.sh migrate:users` | Create Matrix users |
| `./deploy.sh migrate:rooms` | Join archive user to monitored rooms |
| `./deploy.sh migrate:env` | Setup .env from template |

### Utility Commands

| Command | Description |
|---------|-------------|
| `./deploy.sh ssh` | SSH into the server |
| `./deploy.sh logs` | Tail server logs |
| `./deploy.sh status` | Show server status |
| `./deploy.sh db` | Open psql shell |
| `./deploy.sh restart [svc]` | Restart service(s) |
| `./deploy.sh backup` | Run manual backup to S3 |

### Quick Deployment Examples

```bash
# Made a frontend change? Deploy just the web container:
./deploy.sh web

# Made an API change? Deploy just the API:
./deploy.sh api

# Need to restart a service without rebuilding?
./deploy.sh restart api
./deploy.sh restart archive-service

# Check what's happening on the server:
./deploy.sh status
./deploy.sh logs
```

## Development

```bash
# Start infrastructure only
docker compose up -d postgres synapse mautrix-meta

# Run API locally
cd api && pip install -r requirements.txt && uvicorn src.main:app --reload

# Run frontend locally  
cd web && npm install && npm run dev
```

## Troubleshooting

### Bridge won't connect to Messenger

Check mautrix-meta logs:
```bash
docker compose logs mautrix-meta --tail 50
```

Common issues:
- Cookies expired - re-run `login` command
- Facebook blocked the connection - wait and try again

### Messages not appearing in archive

1. Check that the room name matches `ARCHIVE_ROOM_FILTER`
2. Ensure `@archive:archive.local` is invited to the room
3. Check archive-service logs:
   ```bash
   docker compose logs archive-service --tail 50
   ```

### Matrix/Synapse issues

Check Synapse logs:
```bash
docker compose logs synapse --tail 50
```

Reset Synapse (warning: loses all Matrix data):
```bash
docker compose down
docker volume rm messenger-archive_synapse_data
# Recreate the synapse database with proper collation
docker compose up -d postgres
docker exec archive-postgres psql -U archive -d postgres -c "DROP DATABASE IF EXISTS synapse;"
docker exec archive-postgres psql -U archive -d postgres -c "CREATE DATABASE synapse WITH ENCODING 'UTF8' LC_COLLATE='C' LC_CTYPE='C' TEMPLATE=template0;"
docker compose up -d
```

## Tech Stack

- **Frontend**: Next.js 14, TypeScript, React, shadcn/ui, Tailwind CSS
- **Backend**: FastAPI, SQLAlchemy, Python 3.11
- **Database**: PostgreSQL 15
- **Matrix**: Synapse (Element fork), mautrix-meta
- **Deployment**: Docker Compose

## License

MIT
