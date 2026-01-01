# AI Agent Guidelines for Messenger Archive

## Project Overview

This is a self-hosted Messenger archive system that bridges Facebook Messenger to a Matrix homeserver (Synapse), then archives messages to PostgreSQL with a FastAPI backend and Next.js frontend.

**Production URL:** https://mds-archive.duckdns.org  
**Server:** AWS EC2 t3.micro at 98.86.15.121 (user: ubuntu)

## Critical: Production Safety

**This system is actively used in production. Real users rely on it.**

### Before Any Server Operation

1. **Never restart services unnecessarily** - users may be actively using the system
2. **Avoid `docker compose down`** - this takes down all services
3. **Prefer targeted restarts** - use `./deploy.sh restart <service>` instead of restarting everything
4. **Check current usage** - if unsure, ask the user before making changes that could cause downtime

### Safe Operations

- Reading logs: `./deploy.sh logs`
- Checking status: `./deploy.sh status`
- Database queries (SELECT only)
- Deploying individual services: `./deploy.sh web`, `./deploy.sh api`

### Potentially Disruptive Operations (Ask First)

- Restarting services
- Database migrations
- Synapse configuration changes
- Any operation that modifies production data

### Dangerous Operations (Avoid Unless Explicitly Requested)

- `docker compose down`
- `docker compose restart` (all services)
- Dropping/recreating databases
- Modifying Synapse homeserver.yaml without restarting

## Architecture

```
Facebook Messenger
       |
  mautrix-meta (bridge)
       |
  Synapse (Matrix homeserver)
       |
  archive-service (Python) --> PostgreSQL
       |                           |
       +---------------------------+
                   |
            FastAPI Backend
                   |
           Next.js Frontend
```

## Key Services

| Service | Container | Port | Description |
|---------|-----------|------|-------------|
| web | archive-web | 3000 | Next.js frontend |
| api | archive-api | 8000 | FastAPI backend |
| synapse | archive-synapse | 8008 | Matrix homeserver |
| mautrix-meta | archive-mautrix-meta | 29319 | Facebook bridge |
| archive-service | archive-service | - | Message sync service |
| postgres | archive-postgres | 5432 | Database |
| caddy | archive-caddy | 80/443 | Reverse proxy |
| element | archive-element | 8080 | Matrix web client |

## Databases

PostgreSQL contains 3 databases:

1. **messenger_archive** - Main application data
   - `messages` - Archived messages
   - `people` - Senders
   - `rooms` - Chat rooms
   - `discussions` - AI-identified discussion threads
   - `topics` - Topic classifications

2. **synapse** - Matrix homeserver data
   - `events` - All Matrix events
   - `room_memberships` - Room membership state
   - `users` - Matrix users

3. **mautrix_meta** - Facebook bridge data
   - `user` - Bridge users
   - `user_login` - Facebook credentials (cookies)
   - `portal` - Bridged rooms

## Common Tasks

### Deploying Changes

```bash
# Frontend changes
./deploy.sh web

# Backend API changes
./deploy.sh api

# Archive service changes
./deploy.sh archive

# All services (slow, avoid if possible)
./deploy.sh app
```

### Checking Logs

```bash
# All logs
./deploy.sh logs

# Specific service
ssh ubuntu@98.86.15.121 "docker compose -f /opt/messenger-archive/docker-compose.prod.yml logs <service> --tail=50"
```

### Database Access

```bash
# Open psql shell
./deploy.sh db

# Or directly
ssh ubuntu@98.86.15.121 "docker exec -it archive-postgres psql -U archive messenger_archive"
```

### If Archive Service Stops Syncing

1. Check if archive user is in the rooms:
```sql
SELECT user_id, membership FROM room_memberships 
WHERE room_id = '!LMFAEdutdwyDIlPrrW:archive.local' 
AND user_id = '@archive:archive.local';
```

2. If not in room, run: `./deploy.sh migrate:rooms`

3. Check archive-service logs for errors

### If Facebook Bridge Disconnects

1. Check mautrix-meta logs for "No user logins found"
2. May need to re-login via Element (SSH tunnel to port 8080)
3. Or re-migrate credentials: `./deploy.sh migrate:bridge`

## File Locations

### Local Development
- Project root: `/Users/raynor/Documents/00-BUSINESS/messenger-archive`
- Config files: `./config/`

### Production Server
- App root: `/opt/messenger-archive`
- Config: `/opt/messenger-archive/config/`
- Media store: `/opt/messenger-archive/config/synapse/media_store/`
- Env file: `/opt/messenger-archive/.env`

## Environment Variables

Key variables in `.env`:
- `NEXT_PUBLIC_API_URL` - Must be set for frontend builds
- `POSTGRES_PASSWORD` - Database password
- `ARCHIVE_PASSWORD_HASH` - Web UI login password (bcrypt)
- `GEMINI_API_KEY` - For AI features (discussions, topics)

## Matrix Users

| User | Password | Purpose |
|------|----------|---------|
| @archive:archive.local | archivepass123 | Archive service (must be in rooms) |
| @admin:archive.local | adminpass123 | Bridge owner |
| @archiveadmin:archive.local | archiveadmin123 | Server admin for room management |
| @metabot:archive.local | (appservice) | Facebook bridge bot |

## Monitored Rooms

Currently archiving 2 MDS group chats:
- General Chat - Manila Dialectics Society (`!LMFAEdutdwyDIlPrrW:archive.local`)
- Immersion - Manila Dialectics Society (`!mEHaUFRsTPWcvBqsAs:archive.local`)

These are configured in `messenger_archive.rooms` table.
