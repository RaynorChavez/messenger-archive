# Messenger Archive - AWS Deployment Plan

## Overview

Single-machine deployment on AWS EC2 t3.micro (free tier) with:
- Secure access (only you can access your Messenger data)
- Synapse/Matrix completely internal (SSH tunnel only)
- Automated backups to S3
- Memory optimizations for 1GB RAM constraint

---

## 1. Infrastructure

### AWS Free Tier (12 months from Dec 2, 2025)

**What's included:**
- EC2 t3.micro (2 vCPU, 1GB RAM) - 750 hrs/month free
- 30GB EBS storage - free
- S3 - 5GB free
- Data transfer - 100GB/month free

**After free tier expires (~Dec 2026):** ~$8-10/month

---

## 2. Security Architecture

### Network Security

```
Internet
    │
    ├──▶ Port 22 (SSH) ──▶ fail2ban + key-only auth
    │
    ▼ Port 443 (HTTPS only)
┌─────────────────────────────────────────────────┐
│                   Caddy                          │
│         (reverse proxy + auto HTTPS)            │
│                                                  │
│   xxxxx.duckdns.org → web:3000                  │
│   xxxxx.duckdns.org/api/* → api:8000            │
└─────────────────────────────────────────────────┘
    │
    ▼ (internal Docker network only)
┌─────────────────────────────────────────────────┐
│   web ←→ api ←→ postgres                        │
│                    ↑                             │
│   synapse ←→ mautrix-meta                       │
│      ↑              ↑                            │
│      └──── archive-service                      │
│                                                  │
│   element (127.0.0.1:8080 only - SSH tunnel)   │
└─────────────────────────────────────────────────┘
```

**Security measures:**
- ✅ Only ports 22 (SSH) and 443 (HTTPS) exposed to internet
- ✅ Synapse NOT publicly accessible (internal Docker network only)
- ✅ Element Web only accessible via SSH tunnel (127.0.0.1:8080)
- ✅ AWS Security Group firewall (deny all except 22, 443)
- ✅ fail2ban for SSH brute-force protection
- ✅ SSH key-only auth (password disabled)
- ✅ App-level password protection (already implemented)

### Accessing Element Web (if needed for mautrix-meta re-login)

```bash
# SSH tunnel from your local machine
ssh -L 8080:localhost:8080 ubuntu@your-server

# Then open in browser
open http://localhost:8080
```

---

## 3. Memory Optimizations (Critical for 1GB RAM)

### Swap File (2GB)

```bash
# Create 2GB swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Optimize swappiness (prefer RAM, use swap as backup)
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Postgres Tuning

Create `config/postgres/postgresql.conf`:

```ini
# Memory - tuned for 1GB total RAM
shared_buffers = 128MB
effective_cache_size = 256MB
work_mem = 4MB
maintenance_work_mem = 64MB

# Connections
max_connections = 20

# WAL
wal_buffers = 4MB
checkpoint_completion_target = 0.9
```

### Docker Memory Limits

Update docker-compose.prod.yml with memory limits:

```yaml
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 300M
  
  synapse:
    deploy:
      resources:
        limits:
          memory: 200M
  
  api:
    deploy:
      resources:
        limits:
          memory: 150M
  
  web:
    deploy:
      resources:
        limits:
          memory: 150M
  
  mautrix-meta:
    deploy:
      resources:
        limits:
          memory: 100M
  
  archive-service:
    deploy:
      resources:
        limits:
          memory: 100M
  
  caddy:
    deploy:
      resources:
        limits:
          memory: 50M
```

**Total: ~1050MB** - swap will handle overflow

---

## 4. Database Backup to S3

### Setup

```bash
# Install AWS CLI (already on Amazon Linux, or install on Ubuntu)
sudo apt install awscli -y

# Configure with IAM credentials (or use instance role)
aws configure
```

### Backup Script

```bash
#!/bin/bash
# /opt/messenger-archive/scripts/backup.sh
set -e

DATE=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)
DAY_OF_MONTH=$(date +%d)
BACKUP_DIR="/tmp/backups"
S3_BUCKET="messenger-archive-backups-952094707818"

mkdir -p $BACKUP_DIR

# Dump and compress
docker exec archive-postgres pg_dump -U archive messenger_archive | gzip > "${BACKUP_DIR}/daily_${DATE}.sql.gz"

# Upload to S3
aws s3 cp "${BACKUP_DIR}/daily_${DATE}.sql.gz" "s3://${S3_BUCKET}/daily/"

# Weekly backup (Sunday)
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    aws s3 cp "${BACKUP_DIR}/daily_${DATE}.sql.gz" "s3://${S3_BUCKET}/weekly/weekly_${DATE}.sql.gz"
fi

# Monthly backup (1st of month)
if [ "$DAY_OF_MONTH" -eq 01 ]; then
    aws s3 cp "${BACKUP_DIR}/daily_${DATE}.sql.gz" "s3://${S3_BUCKET}/monthly/monthly_${DATE}.sql.gz"
fi

# Cleanup local
rm -rf $BACKUP_DIR

echo "Backup completed: ${DATE}"
```

### S3 Lifecycle Policy (auto-delete old backups)

```json
{
  "Rules": [
    {
      "ID": "DeleteOldDailyBackups",
      "Status": "Enabled",
      "Filter": { "Prefix": "daily/" },
      "Expiration": { "Days": 7 }
    },
    {
      "ID": "DeleteOldWeeklyBackups",
      "Status": "Enabled",
      "Filter": { "Prefix": "weekly/" },
      "Expiration": { "Days": 30 }
    },
    {
      "ID": "DeleteOldMonthlyBackups",
      "Status": "Enabled",
      "Filter": { "Prefix": "monthly/" },
      "Expiration": { "Days": 365 }
    }
  ]
}
```

### Cron Schedule

```bash
# Run daily at 3 AM UTC
0 3 * * * /opt/messenger-archive/scripts/backup.sh >> /var/log/backup.log 2>&1
```

---

## 5. Step-by-Step Deployment

### Phase 1: AWS Setup (15 min)

#### 1.1 Create EC2 Instance

```bash
# Using AWS CLI (or do via Console)
aws ec2 run-instances \
  --image-id ami-0c7217cdde317cfec \  # Ubuntu 22.04 us-east-1
  --instance-type t3.micro \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxx \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=messenger-archive}]'
```

#### 1.2 Create Security Group

```bash
# Create security group
aws ec2 create-security-group \
  --group-name messenger-archive-sg \
  --description "Messenger Archive - SSH and HTTPS only"

# Allow SSH (port 22) - restrict to your IP if possible
aws ec2 authorize-security-group-ingress \
  --group-name messenger-archive-sg \
  --protocol tcp --port 22 --cidr 0.0.0.0/0

# Allow HTTPS (port 443)
aws ec2 authorize-security-group-ingress \
  --group-name messenger-archive-sg \
  --protocol tcp --port 443 --cidr 0.0.0.0/0

# Allow HTTP (port 80) - for Caddy ACME challenge
aws ec2 authorize-security-group-ingress \
  --group-name messenger-archive-sg \
  --protocol tcp --port 80 --cidr 0.0.0.0/0
```

#### 1.3 Allocate Elastic IP (so IP doesn't change)

```bash
aws ec2 allocate-address --domain vpc
# Note the AllocationId

aws ec2 associate-address \
  --instance-id i-xxxxxxxxx \
  --allocation-id eipalloc-xxxxxxxxx
```

### Phase 2: Server Setup (20 min)

```bash
# SSH into server
ssh -i your-key.pem ubuntu@<elastic-ip>

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
newgrp docker

# Install fail2ban
sudo apt install fail2ban -y
sudo systemctl enable fail2ban

# Setup swap (CRITICAL for 1GB RAM)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Verify swap
free -h  # Should show 2GB swap

# Harden SSH
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Create app directory
sudo mkdir -p /opt/messenger-archive
sudo chown ubuntu:ubuntu /opt/messenger-archive
```

### Phase 3: DuckDNS Setup (5 min)

```bash
# 1. Go to duckdns.org, login with GitHub/Google
# 2. Create subdomain (e.g., raynor-archive)
# 3. Point it to your Elastic IP

# 4. Create update script (optional - Elastic IP shouldn't change)
cat > /opt/messenger-archive/scripts/duckdns-update.sh << 'EOF'
#!/bin/bash
curl -s "https://www.duckdns.org/update?domains=YOUR_SUBDOMAIN&token=YOUR_TOKEN&ip="
EOF
chmod +x /opt/messenger-archive/scripts/duckdns-update.sh
```

### Phase 4: Deploy Application (15 min)

```bash
cd /opt/messenger-archive

# Clone repo (or copy files)
git clone https://github.com/YOUR_USERNAME/messenger-archive.git .

# Create .env file
cat > .env << 'EOF'
# Database
POSTGRES_USER=archive
POSTGRES_PASSWORD=<generate-strong-password>
POSTGRES_DB=messenger_archive
DATABASE_URL=postgresql://archive:<same-password>@postgres:5432/messenger_archive

# App Security
ARCHIVE_PASSWORD_HASH=<your-bcrypt-hash>
SESSION_SECRET=<generate-64-char-random-string>

# AI
GEMINI_API_KEY=<your-gemini-key>

# Caddy
DOMAIN=your-subdomain.duckdns.org

# API
API_HOST=0.0.0.0
API_PORT=8000
NEXT_PUBLIC_API_URL=https://your-subdomain.duckdns.org
EOF

# Build and start services
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# Check status
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
```

### Phase 5: Migrate Data (10 min)

```bash
# === ON LOCAL MACHINE ===

# Export database
docker exec archive-postgres pg_dump -U archive messenger_archive | gzip > backup.sql.gz

# Copy to server
scp -i your-key.pem backup.sql.gz ubuntu@<elastic-ip>:/opt/messenger-archive/

# Copy mautrix-meta config (preserves Facebook session!)
scp -i your-key.pem -r ./config/mautrix-meta ubuntu@<elastic-ip>:/opt/messenger-archive/config/

# Copy synapse config
scp -i your-key.pem -r ./config/synapse ubuntu@<elastic-ip>:/opt/messenger-archive/config/

# === ON SERVER ===

# Stop services temporarily
docker compose -f docker-compose.prod.yml stop

# Import database
gunzip -c backup.sql.gz | docker exec -i archive-postgres psql -U archive messenger_archive

# Restart services
docker compose -f docker-compose.prod.yml up -d

# Verify
curl -s https://your-subdomain.duckdns.org/api/health
```

### Phase 6: Setup Backups (10 min)

```bash
# Create S3 bucket
aws s3 mb s3://messenger-archive-backups-952094707818 --region us-east-1

# Apply lifecycle policy
aws s3api put-bucket-lifecycle-configuration \
  --bucket messenger-archive-backups-952094707818 \
  --lifecycle-configuration file://s3-lifecycle.json

# Make backup script executable
chmod +x /opt/messenger-archive/scripts/backup.sh

# Test backup
/opt/messenger-archive/scripts/backup.sh

# Add to crontab
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/messenger-archive/scripts/backup.sh >> /var/log/backup.log 2>&1") | crontab -
```

### Phase 7: CI/CD Setup (Optional, 10 min)

```bash
# On server - create deploy key
ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N ""
cat ~/.ssh/deploy_key.pub >> ~/.ssh/authorized_keys

# In GitHub repo Settings → Secrets → Actions:
# - SERVER_HOST: your-subdomain.duckdns.org
# - SERVER_USER: ubuntu
# - SERVER_SSH_KEY: (contents of ~/.ssh/deploy_key)
```

---

## 6. Monitoring

### Simple Health Check

```bash
# Add to crontab - alert if down
*/5 * * * * curl -sf https://your-subdomain.duckdns.org/api/health || echo "Archive is DOWN" | mail -s "Alert" your@email.com
```

### Memory Monitoring

```bash
# Check memory usage
docker stats --no-stream

# Check swap usage
free -h
```

---

## 7. Maintenance Commands

```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f api

# Restart a service
docker compose -f docker-compose.prod.yml restart api

# Update and redeploy
cd /opt/messenger-archive
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# Access Element Web (for mautrix-meta re-login)
# From your local machine:
ssh -L 8080:localhost:8080 ubuntu@your-server
# Then open http://localhost:8080

# Manual backup
/opt/messenger-archive/scripts/backup.sh

# Restore from backup
aws s3 cp s3://messenger-archive-backups-952094707818/daily/daily_YYYYMMDD_HHMMSS.sql.gz .
gunzip -c daily_*.sql.gz | docker exec -i archive-postgres psql -U archive messenger_archive
```

---

## 8. Cost Summary

| Item | Cost |
|------|------|
| EC2 t3.micro | $0 (free tier, 11 months left) |
| EBS 30GB | $0 (free tier) |
| S3 backups | $0 (under 5GB free) |
| Elastic IP | $0 (attached to running instance) |
| DuckDNS | $0 |
| **Total** | **$0/month** (for 11 months) |

After free tier: ~$8-10/month

---

## 9. Troubleshooting

### Out of Memory

```bash
# Check what's using memory
docker stats --no-stream

# Check swap
free -h

# If swap is full, increase it
sudo swapoff /swapfile
sudo fallocate -l 4G /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Caddy can't get certificate

```bash
# Check Caddy logs
docker compose -f docker-compose.prod.yml logs caddy

# Common issues:
# - Port 80 not open in security group
# - DNS not pointing to server yet (wait 5 min)
# - Rate limited (wait 1 hour)
```

### mautrix-meta disconnected

```bash
# Check bridge status
docker compose -f docker-compose.prod.yml logs mautrix-meta

# If session expired, re-login via Element:
ssh -L 8080:localhost:8080 ubuntu@your-server
# Open http://localhost:8080, login as bridge user, send !meta login
```
