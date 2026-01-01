#!/bin/bash
# Backup script for Messenger Archive
# Backs up all PostgreSQL databases to AWS S3
set -e

DATE=$(date +%Y%m%d_%H%M%S)
DAY_OF_WEEK=$(date +%u)
DAY_OF_MONTH=$(date +%d)
BACKUP_DIR="/tmp/backups"
S3_BUCKET="${S3_BACKUP_BUCKET:-messenger-archive-backups-952094707818}"

mkdir -p $BACKUP_DIR

echo "[$(date)] Starting backup..."

# Backup all 3 databases
DATABASES="messenger_archive synapse mautrix_meta"

for DB in $DATABASES; do
    echo "[$(date)] Backing up $DB..."
    docker exec archive-postgres pg_dump -U archive "$DB" | gzip > "${BACKUP_DIR}/${DB}_${DATE}.sql.gz"
    BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${DB}_${DATE}.sql.gz" | cut -f1)
    echo "[$(date)] $DB dumped: ${BACKUP_SIZE}"
done

# Create combined archive
echo "[$(date)] Creating combined archive..."
tar -czf "${BACKUP_DIR}/daily_${DATE}.tar.gz" -C "${BACKUP_DIR}" \
    "messenger_archive_${DATE}.sql.gz" \
    "synapse_${DATE}.sql.gz" \
    "mautrix_meta_${DATE}.sql.gz"
TOTAL_SIZE=$(du -h "${BACKUP_DIR}/daily_${DATE}.tar.gz" | cut -f1)
echo "[$(date)] Combined archive: ${TOTAL_SIZE}"

# Upload to S3
aws s3 cp "${BACKUP_DIR}/daily_${DATE}.tar.gz" "s3://${S3_BUCKET}/daily/" --quiet
echo "[$(date)] Uploaded to s3://${S3_BUCKET}/daily/"

# Weekly backup (Sunday)
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    aws s3 cp "${BACKUP_DIR}/daily_${DATE}.tar.gz" "s3://${S3_BUCKET}/weekly/weekly_${DATE}.tar.gz" --quiet
    echo "[$(date)] Weekly backup created"
fi

# Monthly backup (1st of month)
if [ "$DAY_OF_MONTH" -eq "01" ]; then
    aws s3 cp "${BACKUP_DIR}/daily_${DATE}.tar.gz" "s3://${S3_BUCKET}/monthly/monthly_${DATE}.tar.gz" --quiet
    echo "[$(date)] Monthly backup created"
fi

# Cleanup local
rm -rf $BACKUP_DIR

echo "[$(date)] Backup completed successfully (all 3 databases)"
