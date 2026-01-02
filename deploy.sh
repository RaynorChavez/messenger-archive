#!/bin/bash
# Deployment script for Messenger Archive
# Usage: ./deploy.sh [command]
#
# Commands:
#   infra          - Deploy AWS infrastructure (EC2, S3) via CDK
#   app            - Deploy application to EC2 (git pull + docker compose)
#   migrate        - Full migration: db + bridge + media (interactive)
#   migrate:db     - Migrate messenger_archive database only
#   migrate:bridge - Migrate mautrix-meta bridge credentials (Facebook login)
#   migrate:media  - Sync Synapse media store
#   migrate:users  - Create Matrix users (archive, admin)
#   backup         - Run a manual backup
#   all            - Deploy infra + app
#
# First time setup:
#   1. Update infra/cdk/config/prod.json with your DuckDNS domain
#   2. Run: ./deploy.sh infra
#   3. Point your DuckDNS domain to the Elastic IP (shown in output)
#   4. SSH to server and create .env file
#   5. Run: ./deploy.sh migrate (or individual migrate:* commands)
#   6. Run: ./deploy.sh app

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMMAND="${1:-help}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Get server IP from CDK outputs
get_server_ip() {
    cd "$SCRIPT_DIR/infra/cdk"
    aws cloudformation describe-stacks \
        --stack-name messenger-archive-compute \
        --query "Stacks[0].Outputs[?OutputKey=='PublicIP'].OutputValue" \
        --output text 2>/dev/null || echo ""
}

# Deploy infrastructure via CDK
deploy_infra() {
    log_step "Deploying AWS infrastructure..."
    
    cd "$SCRIPT_DIR/infra/cdk"
    
    # Check if virtualenv exists
    if [ ! -d ".venv" ]; then
        log_info "Creating Python virtual environment..."
        python3 -m venv .venv
    fi
    
    # Activate and install deps
    source .venv/bin/activate
    pip install -q -r requirements.txt
    
    # Bootstrap if needed (first time only)
    if ! aws cloudformation describe-stacks --stack-name CDKToolkit &>/dev/null; then
        log_info "Bootstrapping CDK (first time only)..."
        cdk bootstrap
    fi
    
    # Deploy
    log_info "Running CDK deploy..."
    ENVIRONMENT=prod cdk deploy --all --require-approval never
    
    # Show outputs
    echo ""
    log_info "Infrastructure deployed!"
    echo ""
    
    SERVER_IP=$(get_server_ip)
    if [ -n "$SERVER_IP" ]; then
        echo -e "${GREEN}=== NEXT STEPS ===${NC}"
        echo "1. Point your DuckDNS domain to: $SERVER_IP"
        echo "2. Wait a few minutes for the server to finish setup"
        echo "3. Run: ./deploy.sh migrate"
        echo "4. Run: ./deploy.sh app"
        echo ""
        echo "SSH command: ssh ubuntu@$SERVER_IP"
    fi
    
    deactivate
}

# Deploy application to server (all services)
deploy_app() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    log_step "Deploying application to $SERVER_IP..."
    
    # Note: We use a regular heredoc (not 'ENDSSH') so that variables are expanded
    # The NEXT_PUBLIC_API_URL is read from the server's .env file
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        set -e
        cd /opt/messenger-archive
        
        echo "=== Pulling latest code ==="
        git fetch origin main
        git reset --hard origin/main
        
        # Load the API URL from .env for the build
        if [ -f .env ]; then
            export $(grep NEXT_PUBLIC_API_URL .env | xargs)
        fi
        
        if [ -z "$NEXT_PUBLIC_API_URL" ]; then
            echo "ERROR: NEXT_PUBLIC_API_URL not set in .env"
            exit 1
        fi
        
        echo "=== Building containers (API URL: $NEXT_PUBLIC_API_URL) ==="
        # Pass the API URL as a build arg for the web container
        NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" docker compose -f docker-compose.prod.yml build --pull
        
        echo "=== Restarting services ==="
        docker compose -f docker-compose.prod.yml up -d
        
        echo "=== Cleaning up ==="
        docker image prune -f
        
        echo "=== Status ==="
        docker compose -f docker-compose.prod.yml ps
        free -h
ENDSSH
    
    log_info "Application deployed!"
}

# Deploy frontend only (Next.js)
deploy_web() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    log_step "Deploying frontend to $SERVER_IP..."
    
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        set -e
        cd /opt/messenger-archive
        
        echo "=== Pulling latest code ==="
        git fetch origin main
        git reset --hard origin/main
        
        # Load the API URL from .env for the build
        if [ -f .env ]; then
            export $(grep NEXT_PUBLIC_API_URL .env | xargs)
        fi
        
        if [ -z "$NEXT_PUBLIC_API_URL" ]; then
            echo "ERROR: NEXT_PUBLIC_API_URL not set in .env"
            exit 1
        fi
        
        echo "=== Building frontend (API URL: $NEXT_PUBLIC_API_URL) ==="
        NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" docker compose -f docker-compose.prod.yml build web
        
        echo "=== Restarting frontend ==="
        docker compose -f docker-compose.prod.yml up -d web
        
        echo "=== Cleaning up ==="
        docker image prune -f
        
        echo "=== Done ==="
        docker compose -f docker-compose.prod.yml ps web
ENDSSH
    
    log_info "Frontend deployed!"
}

# Deploy backend only (FastAPI)
deploy_api() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    log_step "Deploying API to $SERVER_IP..."
    
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        set -e
        cd /opt/messenger-archive
        
        echo "=== Pulling latest code ==="
        git fetch origin main
        git reset --hard origin/main
        
        echo "=== Building API ==="
        docker compose -f docker-compose.prod.yml build api
        
        echo "=== Restarting API ==="
        docker compose -f docker-compose.prod.yml up -d api
        
        echo "=== Cleaning up ==="
        docker image prune -f
        
        echo "=== Done ==="
        docker compose -f docker-compose.prod.yml ps api
ENDSSH
    
    log_info "API deployed!"
}

# Deploy archive-service only
deploy_archive() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    log_step "Deploying archive-service to $SERVER_IP..."
    
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        set -e
        cd /opt/messenger-archive
        
        echo "=== Pulling latest code ==="
        git fetch origin main
        git reset --hard origin/main
        
        echo "=== Building archive-service ==="
        docker compose -f docker-compose.prod.yml build archive-service
        
        echo "=== Restarting archive-service ==="
        docker compose -f docker-compose.prod.yml up -d archive-service
        
        echo "=== Cleaning up ==="
        docker image prune -f
        
        echo "=== Done ==="
        docker compose -f docker-compose.prod.yml ps archive-service
ENDSSH
    
    log_info "Archive-service deployed!"
}

# Check server prerequisites
check_server() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    echo "$SERVER_IP"
}

# Check local containers are running
check_local() {
    if ! docker ps | grep -q archive-postgres; then
        log_error "Local postgres container not running. Start with 'docker compose up -d'"
        exit 1
    fi
}

# Migrate messenger_archive database
migrate_db() {
    SERVER_IP=$(check_server)
    check_local
    
    log_step "Migrating messenger_archive database to $SERVER_IP..."
    
    # Export database
    log_info "Exporting local database..."
    docker exec archive-postgres pg_dump -U archive messenger_archive | gzip > /tmp/messenger-archive-backup.sql.gz
    BACKUP_SIZE=$(du -h /tmp/messenger-archive-backup.sql.gz | cut -f1)
    log_info "Database exported: $BACKUP_SIZE"
    
    # Copy to server
    log_info "Copying database to server..."
    scp /tmp/messenger-archive-backup.sql.gz ubuntu@"$SERVER_IP":/tmp/
    
    # Import on server
    log_info "Importing database on server..."
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        set -e
        cd /opt/messenger-archive
        
        # Ensure postgres is running
        docker compose -f docker-compose.prod.yml up -d postgres
        sleep 5
        
        # Drop and recreate database to ensure clean import
        docker exec archive-postgres psql -U archive -d postgres -c "DROP DATABASE IF EXISTS messenger_archive;"
        docker exec archive-postgres psql -U archive -d postgres -c "CREATE DATABASE messenger_archive;"
        
        # Import
        gunzip -c /tmp/messenger-archive-backup.sql.gz | docker exec -i archive-postgres psql -U archive messenger_archive
        
        rm /tmp/messenger-archive-backup.sql.gz
        echo "Database imported successfully!"
ENDSSH
    
    rm /tmp/messenger-archive-backup.sql.gz
    log_info "Database migration complete!"
}

# Migrate mautrix-meta bridge credentials (Facebook login)
migrate_bridge() {
    SERVER_IP=$(check_server)
    check_local
    
    log_step "Migrating mautrix-meta bridge credentials to $SERVER_IP..."
    
    # Export user and user_login tables from local mautrix_meta database
    log_info "Exporting bridge credentials from local..."
    docker exec archive-postgres pg_dump -U archive -d mautrix_meta -t user -t user_login --data-only --inserts > /tmp/mautrix-users.sql
    
    if [ ! -s /tmp/mautrix-users.sql ]; then
        log_warn "No bridge credentials found locally. You may need to login via Element."
        rm -f /tmp/mautrix-users.sql
        return 0
    fi
    
    # Copy to server
    scp /tmp/mautrix-users.sql ubuntu@"$SERVER_IP":/tmp/
    
    # Import on server
    log_info "Importing bridge credentials on server..."
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        set -e
        cd /opt/messenger-archive
        
        # Ensure services are running
        docker compose -f docker-compose.prod.yml up -d postgres mautrix-meta
        sleep 5
        
        # Clear existing and import
        docker exec archive-postgres psql -U archive -d mautrix_meta -c "DELETE FROM user_login;"
        docker exec archive-postgres psql -U archive -d mautrix_meta -c "DELETE FROM \"user\";"
        docker exec -i archive-postgres psql -U archive -d mautrix_meta < /tmp/mautrix-users.sql
        
        # Restart mautrix-meta to pick up the credentials
        docker compose -f docker-compose.prod.yml restart mautrix-meta
        
        rm /tmp/mautrix-users.sql
        echo "Bridge credentials imported successfully!"
ENDSSH
    
    rm /tmp/mautrix-users.sql
    log_info "Bridge migration complete!"
}

# Sync Synapse media store
migrate_media() {
    SERVER_IP=$(check_server)
    
    log_step "Syncing Synapse media store to $SERVER_IP..."
    
    LOCAL_MEDIA="$SCRIPT_DIR/config/synapse/media_store"
    
    if [ ! -d "$LOCAL_MEDIA" ]; then
        log_warn "No local media store found at $LOCAL_MEDIA"
        return 0
    fi
    
    # Get size
    MEDIA_SIZE=$(du -sh "$LOCAL_MEDIA" 2>/dev/null | cut -f1)
    log_info "Syncing media store ($MEDIA_SIZE)..."
    
    # Ensure remote directory exists
    ssh ubuntu@"$SERVER_IP" "mkdir -p /opt/messenger-archive/config/synapse/media_store"
    
    # Rsync media (this preserves existing files and only copies new/changed ones)
    rsync -avz --progress \
        "$LOCAL_MEDIA/" \
        ubuntu@"$SERVER_IP":/opt/messenger-archive/config/synapse/media_store/
    
    # Also sync the Synapse media database tables
    log_info "Syncing Synapse media database tables..."
    docker exec archive-postgres pg_dump -U archive -d synapse \
        -t local_media_repository \
        -t local_media_repository_thumbnails \
        --data-only --inserts > /tmp/synapse-media-tables.sql
    
    if [ -s /tmp/synapse-media-tables.sql ]; then
        scp /tmp/synapse-media-tables.sql ubuntu@"$SERVER_IP":/tmp/
        ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
            set -e
            cd /opt/messenger-archive
            docker compose -f docker-compose.prod.yml up -d postgres synapse
            sleep 5
            # Import media tables (ignore errors for duplicates)
            docker exec -i archive-postgres psql -U archive -d synapse < /tmp/synapse-media-tables.sql 2>/dev/null || true
            rm /tmp/synapse-media-tables.sql
ENDSSH
        rm /tmp/synapse-media-tables.sql
    fi
    
    log_info "Media sync complete!"
}

# Create Matrix users on production
migrate_users() {
    SERVER_IP=$(check_server)
    
    log_step "Creating Matrix users on $SERVER_IP..."
    
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        set -e
        cd /opt/messenger-archive
        
        # Add rate limit config to Synapse if not present
        if ! grep -q "rc_login:" /opt/messenger-archive/config/synapse/homeserver.yaml 2>/dev/null; then
            echo "Adding rate limit config to Synapse..."
            sudo tee -a /opt/messenger-archive/config/synapse/homeserver.yaml > /dev/null << 'RATELIMIT'

# Disable rate limiting for local services
rc_login:
  address:
    per_second: 1000
    burst_count: 1000
  account:
    per_second: 1000
    burst_count: 1000
  failed_attempts:
    per_second: 1000
    burst_count: 1000

rc_message:
  per_second: 1000
  burst_count: 1000

rc_registration:
  per_second: 1000
  burst_count: 1000

rc_joins:
  local:
    per_second: 1000
    burst_count: 1000
  remote:
    per_second: 1000
    burst_count: 1000
RATELIMIT
        fi
        
        # Ensure synapse is running
        docker compose -f docker-compose.prod.yml up -d synapse
        sleep 10
        
        echo "Creating @archive user (for archive-service)..."
        docker exec archive-synapse register_new_matrix_user \
            -c /data/homeserver.yaml \
            -u archive \
            -p archivepass123 \
            -a 2>/dev/null || echo "User @archive may already exist"
        
        echo "Creating @admin user (for mautrix-meta bridge)..."
        docker exec archive-synapse register_new_matrix_user \
            -c /data/homeserver.yaml \
            -u admin \
            -p adminpass123 \
            -a 2>/dev/null || echo "User @admin may already exist"
        
        echo "Matrix users created!"
ENDSSH
    
    log_info "Matrix users created!"
}

# Copy config files to server
migrate_configs() {
    SERVER_IP=$(check_server)
    
    log_step "Copying config files to $SERVER_IP..."
    
    # Copy config directories
    scp -r "$SCRIPT_DIR/config/mautrix-meta" ubuntu@"$SERVER_IP":/opt/messenger-archive/config/
    scp -r "$SCRIPT_DIR/config/synapse" ubuntu@"$SERVER_IP":/opt/messenger-archive/config/
    scp -r "$SCRIPT_DIR/config/element" ubuntu@"$SERVER_IP":/opt/messenger-archive/config/
    
    log_info "Config files copied!"
}

# Setup .env file on server
migrate_env() {
    SERVER_IP=$(check_server)
    
    log_step "Setting up .env file on $SERVER_IP..."
    
    # Check if .env.example exists locally
    if [ ! -f "$SCRIPT_DIR/.env.example" ]; then
        log_error "No .env.example found locally"
        exit 1
    fi
    
    # Check if .env already exists on server
    if ssh ubuntu@"$SERVER_IP" "test -f /opt/messenger-archive/.env"; then
        log_warn ".env already exists on server"
        read -p "Overwrite with .env.example template? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Keeping existing .env"
            return 0
        fi
    fi
    
    # Copy .env.example to server as .env
    log_info "Copying .env.example to server..."
    scp "$SCRIPT_DIR/.env.example" ubuntu@"$SERVER_IP":/opt/messenger-archive/.env
    
    log_info ".env created on server!"
    echo ""
    echo "IMPORTANT: Edit the .env file on the server to set:"
    echo "  - NEXT_PUBLIC_API_URL (your domain)"
    echo "  - POSTGRES_PASSWORD"
    echo "  - ARCHIVE_PASSWORD_HASH (generate with: htpasswd -nbBC 10 '' 'yourpassword' | tr -d ':')"
    echo ""
    echo "Run: ssh ubuntu@$SERVER_IP nano /opt/messenger-archive/.env"
}

# Join archive user to monitored rooms
migrate_room_access() {
    SERVER_IP=$(check_server)
    
    log_step "Joining archive user to monitored rooms on $SERVER_IP..."
    
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        set -e
        cd /opt/messenger-archive
        
        # Ensure services are running
        docker compose -f docker-compose.prod.yml up -d synapse postgres
        sleep 5
        
        # Create an admin user if it doesn't exist
        echo "Ensuring admin user exists..."
        docker exec archive-synapse register_new_matrix_user \
            -c /data/homeserver.yaml \
            -u archiveadmin \
            -p archiveadmin123 \
            -a 2>/dev/null || true
        
        # Make archive user a server admin (needed for room access)
        docker exec archive-postgres psql -U archive -d synapse -c \
            "UPDATE users SET admin = 1 WHERE name = '@archive:archive.local';" 2>/dev/null || true
        
        # Get admin token
        ADMIN_TOKEN=$(docker compose -f docker-compose.prod.yml exec -T synapse curl -s \
            -X POST 'http://localhost:8008/_matrix/client/v3/login' \
            -H 'Content-Type: application/json' \
            -d '{"type": "m.login.password", "user": "archiveadmin", "password": "archiveadmin123"}' \
            | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
        
        if [ -z "$ADMIN_TOKEN" ]; then
            echo "Warning: Could not get admin token. Room access may need manual setup."
            exit 0
        fi
        
        # Get archive user token
        ARCHIVE_TOKEN=$(docker compose -f docker-compose.prod.yml exec -T synapse curl -s \
            -X POST 'http://localhost:8008/_matrix/client/v3/login' \
            -H 'Content-Type: application/json' \
            -d '{"type": "m.login.password", "user": "archive", "password": "archivepass123"}' \
            | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
        
        # Get room IDs from messenger_archive database
        ROOMS=$(docker exec archive-postgres psql -U archive -d messenger_archive -t -c \
            "SELECT matrix_room_id FROM rooms;")
        
        for ROOM_ID in $ROOMS; do
            ROOM_ID=$(echo "$ROOM_ID" | tr -d ' ')
            if [ -n "$ROOM_ID" ]; then
                echo "Processing room: $ROOM_ID"
                
                # URL encode the room ID
                ENCODED_ROOM=$(echo "$ROOM_ID" | sed 's/!/%21/g' | sed 's/:/%3A/g')
                
                # Check if room exists in Synapse
                ROOM_EXISTS=$(docker exec archive-postgres psql -U archive -d synapse -t -c \
                    "SELECT COUNT(*) FROM room_stats_state WHERE room_id = '$ROOM_ID';" | tr -d ' ')
                
                if [ "$ROOM_EXISTS" = "0" ]; then
                    echo "  Room $ROOM_ID not yet synced to Synapse, skipping..."
                    continue
                fi
                
                # Use admin API to make archive user a room admin (this also joins them)
                echo "  Adding archive user to room..."
                docker compose -f docker-compose.prod.yml exec -T synapse curl -s \
                    -X POST "http://localhost:8008/_synapse/admin/v1/rooms/$ENCODED_ROOM/make_room_admin" \
                    -H "Authorization: Bearer $ADMIN_TOKEN" \
                    -H 'Content-Type: application/json' \
                    -d '{"user_id": "@archive:archive.local"}' || true
                
                # Accept any pending invite
                if [ -n "$ARCHIVE_TOKEN" ]; then
                    docker compose -f docker-compose.prod.yml exec -T synapse curl -s \
                        -X POST "http://localhost:8008/_matrix/client/v3/join/$ENCODED_ROOM" \
                        -H "Authorization: Bearer $ARCHIVE_TOKEN" \
                        -H 'Content-Type: application/json' \
                        -d '{}' || true
                fi
                
                echo "  Done"
            fi
        done
        
        echo "Room access setup complete!"
        
        # Restart archive-service to pick up new room memberships
        echo "Restarting archive-service..."
        docker compose -f docker-compose.prod.yml restart archive-service
ENDSSH
    
    log_info "Room access migration complete!"
}

# Full migration (interactive)
migrate_data() {
    SERVER_IP=$(check_server)
    check_local
    
    log_step "Starting full migration to $SERVER_IP..."
    echo ""
    echo "This will migrate:"
    echo "  1. Config files (mautrix-meta, synapse, element)"
    echo "  2. messenger_archive database"
    echo "  3. Matrix users (archive, admin)"
    echo "  4. mautrix-meta bridge credentials (Facebook login)"
    echo "  5. Synapse media store"
    echo "  6. Room access (join archive user to monitored rooms)"
    echo ""
    read -p "Continue? (y/N) " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Migration cancelled."
        exit 0
    fi
    
    # Ensure server has basic setup
    log_info "Checking server setup..."
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        set -e
        cd /opt/messenger-archive
        
        if [ ! -f ".env" ]; then
            echo ""
            echo "ERROR: .env file not found on server!"
            echo "Create /opt/messenger-archive/.env first."
            exit 1
        fi
        
        # Start postgres first
        docker compose -f docker-compose.prod.yml up -d postgres
        echo "Waiting for postgres..."
        sleep 10
ENDSSH
    
    # Run all migrations
    migrate_configs
    migrate_db
    migrate_users
    migrate_bridge
    migrate_media
    migrate_room_access
    
    # Start all services
    log_info "Starting all services..."
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        cd /opt/messenger-archive
        docker compose -f docker-compose.prod.yml up -d
        sleep 5
        docker compose -f docker-compose.prod.yml ps
ENDSSH
    
    log_info "Full migration complete!"
    echo ""
    echo "Verify the deployment:"
    echo "  1. Check status: ./deploy.sh status"
    echo "  2. Check logs: ./deploy.sh logs"
    echo "  3. Visit: https://your-domain.duckdns.org"
}

# Run manual backup
run_backup() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    log_step "Running backup on $SERVER_IP..."
    
    ssh ubuntu@"$SERVER_IP" "/opt/messenger-archive/scripts/backup.sh"
    
    log_info "Backup complete!"
}

# Backfill media info from Synapse and process images
backfill_media() {
    SERVER_IP=$(get_server_ip)
    LIMIT="${1:-1000}"
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    log_step "Backfilling media info on $SERVER_IP (limit: $LIMIT)..."
    
    # Step 1: Backfill media metadata from Synapse
    ssh ubuntu@"$SERVER_IP" << ENDSSH
        set -e
        cd /opt/messenger-archive
        
        echo "=== Step 1: Backfill media metadata from Synapse ==="
        cat scripts/backfill_media.py | docker exec -i archive-api python - --limit $LIMIT
        
        echo ""
        echo "=== Step 2: Process pending images through Gemini Vision ==="
        docker exec archive-api python -c "
from src.db import SessionLocal, ImageDescription
from src.services.image_description import init_image_description_service, get_image_description_service
import os

api_key = os.environ.get('GEMINI_API_KEY')
if not api_key:
    print('ERROR: No GEMINI_API_KEY found')
    exit(1)

init_image_description_service(api_key)
service = get_image_description_service()
db = SessionLocal()

# Get pending count
pending = db.query(ImageDescription).filter(
    ImageDescription.processed_at.is_(None),
    ImageDescription.error.is_(None)
).count()

print(f'Processing {pending} pending images...')

processed = service.process_pending_images(db, limit=$LIMIT)
print(f'Successfully processed {processed} images')

# Show any errors
errors = db.query(ImageDescription).filter(ImageDescription.error.isnot(None)).count()
if errors > 0:
    print(f'Warning: {errors} images failed processing')

db.close()
"
        
        echo ""
        echo "=== Done ==="
ENDSSH
    
    log_info "Media backfill complete!"
}

# Show help
show_help() {
    echo "Messenger Archive Deployment Script"
    echo ""
    echo "Usage: ./deploy.sh [command]"
    echo ""
    echo "Commands:"
    echo "  infra           Deploy AWS infrastructure (EC2, S3) via CDK"
    echo "  app             Deploy all services (git pull + build + restart)"
    echo "  web             Deploy frontend only (Next.js)"
    echo "  api             Deploy backend only (FastAPI)"
    echo "  archive         Deploy archive-service only"
    echo "  migrate         Full migration: db + bridge + media + rooms (interactive)"
    echo "  migrate:db      Migrate messenger_archive database only"
    echo "  migrate:bridge  Migrate mautrix-meta bridge credentials (Facebook login)"
    echo "  migrate:media   Sync Synapse media store"
    echo "  migrate:users   Create Matrix users (archive, admin)"
    echo "  migrate:rooms   Join archive user to monitored rooms"
    echo "  migrate:env     Setup .env file on server from template"
    echo "  backup          Run a manual backup to S3"
    echo "  backfill-media  Backfill media info from Synapse and process images (default: 1000)"
    echo "  all             Deploy infra + wait + app"
    echo "  ssh             SSH into the server"
    echo "  logs            Show server logs"
    echo "  db              Open psql shell (local or remote)"
    echo "  status          Show server status"
    echo "  restart [svc]   Restart service (or all if none specified)"
    echo ""
    echo "Services: api, web, archive-service, pgbouncer, postgres, synapse, mautrix-meta, caddy"
    echo ""
    echo "First time setup:"
    echo "  1. Update infra/cdk/config/prod.json with your DuckDNS domain"
    echo "  2. ./deploy.sh infra"
    echo "  3. Point DuckDNS to the Elastic IP shown in output"
    echo "  4. SSH to server and create .env file"
    echo "  5. ./deploy.sh migrate"
    echo "  6. ./deploy.sh app"
}

# SSH into server
ssh_server() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    ssh ubuntu@"$SERVER_IP"
}

# Show logs
show_logs() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    ssh ubuntu@"$SERVER_IP" "cd /opt/messenger-archive && docker compose -f docker-compose.prod.yml logs -f --tail=100"
}

# Open psql shell
open_db() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        # No server, use local
        log_info "Opening local database..."
        docker exec -it archive-postgres psql -U archive messenger_archive
    else
        log_info "Opening database on $SERVER_IP..."
        ssh -t ubuntu@"$SERVER_IP" "docker exec -it archive-postgres psql -U archive messenger_archive"
    fi
}

# Restart a specific service or all services
restart_service() {
    SERVER_IP=$(get_server_ip)
    SERVICE="${1:-}"
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    if [ -z "$SERVICE" ]; then
        log_step "Restarting all services on $SERVER_IP..."
        ssh ubuntu@"$SERVER_IP" "cd /opt/messenger-archive && docker compose -f docker-compose.prod.yml restart"
    else
        log_step "Restarting $SERVICE on $SERVER_IP..."
        ssh ubuntu@"$SERVER_IP" "cd /opt/messenger-archive && docker compose -f docker-compose.prod.yml restart $SERVICE"
    fi
    
    log_info "Restart complete!"
}

# Show status
show_status() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    echo "Server IP: $SERVER_IP"
    echo ""
    ssh ubuntu@"$SERVER_IP" << 'ENDSSH'
        echo "=== Memory ==="
        free -h
        echo ""
        echo "=== Disk ==="
        df -h /
        echo ""
        echo "=== Containers ==="
        cd /opt/messenger-archive && docker compose -f docker-compose.prod.yml ps
ENDSSH
}

# Main
case "$COMMAND" in
    infra)
        deploy_infra
        ;;
    app)
        deploy_app
        ;;
    web)
        deploy_web
        ;;
    api)
        deploy_api
        ;;
    archive)
        deploy_archive
        ;;
    migrate)
        migrate_data
        ;;
    migrate:db)
        migrate_db
        ;;
    migrate:bridge)
        migrate_bridge
        ;;
    migrate:media)
        migrate_media
        ;;
    migrate:users)
        migrate_users
        ;;
    migrate:rooms)
        migrate_room_access
        ;;
    migrate:env)
        migrate_env
        ;;
    backup)
        run_backup
        ;;
    backfill-media)
        backfill_media "${2:-1000}"
        ;;
    all)
        deploy_infra
        log_info "Waiting 60 seconds for server to initialize..."
        sleep 60
        deploy_app
        ;;
    ssh)
        ssh_server
        ;;
    logs)
        show_logs
        ;;
    db)
        open_db
        ;;
    status)
        show_status
        ;;
    restart)
        restart_service "${2:-}"
        ;;
    help|--help|-h|"")
        show_help
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac
