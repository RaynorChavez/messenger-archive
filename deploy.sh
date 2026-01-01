#!/bin/bash
# Deployment script for Messenger Archive
# Usage: ./deploy.sh [infra|app|migrate|backup|all]
#
# Commands:
#   infra   - Deploy AWS infrastructure (EC2, S3) via CDK
#   app     - Deploy application to EC2 (git pull + docker compose)
#   migrate - Migrate data from local to server
#   backup  - Run a manual backup
#   all     - Deploy infra + app
#
# First time setup:
#   1. Update infra/cdk/config/prod.json with your DuckDNS domain
#   2. Run: ./deploy.sh infra
#   3. Point your DuckDNS domain to the Elastic IP (shown in output)
#   4. Run: ./deploy.sh migrate
#   5. Run: ./deploy.sh app

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

# Deploy application to server
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

# Migrate data from local to server
migrate_data() {
    SERVER_IP=$(get_server_ip)
    
    if [ -z "$SERVER_IP" ]; then
        log_error "Could not find server IP. Run './deploy.sh infra' first."
        exit 1
    fi
    
    log_step "Migrating data to $SERVER_IP..."
    
    # Check if local containers are running
    if ! docker ps | grep -q archive-postgres; then
        log_error "Local postgres container not running. Start with 'docker compose up -d'"
        exit 1
    fi
    
    # Export database
    log_info "Exporting local database..."
    docker exec archive-postgres pg_dump -U archive messenger_archive | gzip > /tmp/messenger-archive-backup.sql.gz
    BACKUP_SIZE=$(du -h /tmp/messenger-archive-backup.sql.gz | cut -f1)
    log_info "Database exported: $BACKUP_SIZE"
    
    # Copy files to server
    log_info "Copying files to server..."
    scp /tmp/messenger-archive-backup.sql.gz ubuntu@"$SERVER_IP":/opt/messenger-archive/
    scp -r "$SCRIPT_DIR/config/mautrix-meta" ubuntu@"$SERVER_IP":/opt/messenger-archive/config/
    scp -r "$SCRIPT_DIR/config/synapse" ubuntu@"$SERVER_IP":/opt/messenger-archive/config/
    scp -r "$SCRIPT_DIR/config/element" ubuntu@"$SERVER_IP":/opt/messenger-archive/config/
    
    # Clone repo and setup on server
    log_info "Setting up application on server..."
    ssh ubuntu@"$SERVER_IP" << ENDSSH
        set -e
        cd /opt/messenger-archive
        
        # Clone repo if not exists
        if [ ! -d ".git" ]; then
            echo "Cloning repository..."
            git clone https://github.com/YOUR_USERNAME/messenger-archive.git .
        fi
        
        # Check if .env exists
        if [ ! -f ".env" ]; then
            echo ""
            echo "ERROR: .env file not found!"
            echo "Create /opt/messenger-archive/.env with your configuration."
            echo "See .env.example for reference."
            exit 1
        fi
        
        echo "Starting services..."
        docker compose -f docker-compose.prod.yml up -d postgres
        
        echo "Waiting for postgres to be ready..."
        sleep 10
        
        echo "Importing database..."
        gunzip -c messenger-archive-backup.sql.gz | docker exec -i archive-postgres psql -U archive messenger_archive
        
        echo "Starting all services..."
        docker compose -f docker-compose.prod.yml up -d
        
        echo "Cleaning up..."
        rm messenger-archive-backup.sql.gz
ENDSSH
    
    # Cleanup local temp file
    rm /tmp/messenger-archive-backup.sql.gz
    
    log_info "Migration complete!"
    echo ""
    echo "Next steps:"
    echo "1. SSH to server: ssh ubuntu@$SERVER_IP"
    echo "2. Create .env file if not done: nano /opt/messenger-archive/.env"
    echo "3. Verify services: docker compose -f docker-compose.prod.yml ps"
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

# Show help
show_help() {
    echo "Messenger Archive Deployment Script"
    echo ""
    echo "Usage: ./deploy.sh [command]"
    echo ""
    echo "Commands:"
    echo "  infra    Deploy AWS infrastructure (EC2, S3) via CDK"
    echo "  app      Deploy application to EC2 (git pull + docker compose)"
    echo "  migrate  Migrate data from local to server"
    echo "  backup   Run a manual backup to S3"
    echo "  all      Deploy infra + wait + app"
    echo "  ssh      SSH into the server"
    echo "  logs     Show server logs"
    echo "  db       Open psql shell (local or remote)"
    echo "  status   Show server status"
    echo ""
    echo "First time setup:"
    echo "  1. Update infra/cdk/config/prod.json with your DuckDNS domain"
    echo "  2. ./deploy.sh infra"
    echo "  3. Point DuckDNS to the Elastic IP shown in output"
    echo "  4. SSH to server and create .env file"
    echo "  5. ./deploy.sh migrate"
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
    migrate)
        migrate_data
        ;;
    backup)
        run_backup
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
    help|--help|-h|"")
        show_help
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac
