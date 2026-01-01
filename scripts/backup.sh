#!/bin/bash
# Backup script for Messenger Archive
# Backs up PostgreSQL database to AWS S3
set -e

DATE=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)
DAY_OF_MONTH=$(date +%d)
BACKUP_DIR="/tmp/backups"
S3_BUCKET="${S3_BACKUP_BUCKET:-messenger-archive-backups-952094707818}"

mkdir -p $BACKUP_DIR

echo "[$(date)] Starting backup..."

# Dump and compress
docker exec archive-postgres pg_dump -U archive messenger_archive | gzip > "${BACKUP_DIR}/daily_${DATE}.sql.gz"
BACKUP_SIZE=$(du -h "${BACKUP_DIR}/daily_${DATE}.sql.gz" | cut -f1)
echo "[$(date)] Database dumped: ${BACKUP_SIZE}"

# Upload to S3
aws s3 cp "${BACKUP_DIR}/daily_${DATE}.sql.gz" "s3://${S3_BUCKET}/daily/" --quiet
echo "[$(date)] Uploaded to s3://${S3_BUCKET}/daily/"

# Weekly backup (Sunday)
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    aws s3 cp "${BACKUP_DIR}/daily_${DATE}.sql.gz" "s3://${S3_BUCKET}/weekly/weekly_${DATE}.sql.gz" --quiet
    echo "[$(date)] Weekly backup created"
fi

# Monthly backup (1st of month)
if [ "$DAY_OF_MONTH" -eq "01" ]; then
    aws s3 cp "${BACKUP_DIR}/daily_${DATE}.sql.gz" "s3://${S3_BUCKET}/monthly/monthly_${DATE}.sql.gz" --quiet
    echo "[$(date)] Monthly backup created"
fi

# Cleanup local
rm -rf $BACKUP_DIR

echo "[$(date)] Backup completed successfully"
