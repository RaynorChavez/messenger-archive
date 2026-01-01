"""S3 storage stack for Messenger Archive backups."""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_s3 as s3,
    Duration,
    RemovalPolicy,
)
from constructs import Construct

from config.base import ArchiveConfig


class StorageStack(cdk.Stack):
    """Stack for S3 backup bucket with lifecycle rules."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: ArchiveConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket for backups
        self.backup_bucket = s3.Bucket(
            self,
            "BackupBucket",
            bucket_name=config.bucket_name,
            removal_policy=RemovalPolicy.RETAIN,  # Don't delete backups if stack is destroyed
            auto_delete_objects=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=False,  # We handle versioning via daily/weekly/monthly prefixes
            lifecycle_rules=[
                # Daily backups - keep 7 days
                s3.LifecycleRule(
                    id="DeleteOldDailyBackups",
                    prefix="daily/",
                    expiration=Duration.days(7),
                ),
                # Weekly backups - keep 30 days
                s3.LifecycleRule(
                    id="DeleteOldWeeklyBackups",
                    prefix="weekly/",
                    expiration=Duration.days(30),
                ),
                # Monthly backups - keep 365 days
                s3.LifecycleRule(
                    id="DeleteOldMonthlyBackups",
                    prefix="monthly/",
                    expiration=Duration.days(365),
                ),
            ],
        )

        # Outputs
        cdk.CfnOutput(
            self,
            "BackupBucketName",
            value=self.backup_bucket.bucket_name,
            description="S3 bucket for database backups",
        )

        cdk.CfnOutput(
            self,
            "BackupBucketArn",
            value=self.backup_bucket.bucket_arn,
            description="S3 bucket ARN",
        )
