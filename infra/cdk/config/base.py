"""Configuration management for Messenger Archive CDK stacks."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ArchiveConfig:
    """Configuration for Messenger Archive infrastructure.

    Attributes:
        env: Environment name ("prod" only for now)
        aws_account_id: AWS account ID for deployment
        aws_region: AWS region for deployment
        ssh_key_name: Name of SSH key pair in AWS
        domain: DuckDNS domain (optional, e.g., raynor-archive.duckdns.org)
    """

    env: str
    aws_account_id: str
    aws_region: str
    ssh_key_name: str
    domain: Optional[str] = None

    @property
    def resource_prefix(self) -> str:
        """Resource naming prefix."""
        return "messenger-archive"

    @property
    def bucket_name(self) -> str:
        """S3 bucket name for backups."""
        return f"{self.resource_prefix}-backups-{self.aws_account_id}"


def load_config(env: Optional[str] = None) -> ArchiveConfig:
    """Load configuration for the specified environment.

    Args:
        env: Environment name. Defaults to ENVIRONMENT env var or "prod".

    Returns:
        ArchiveConfig instance for the environment.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config file is invalid.
    """
    env = env or os.getenv("ENVIRONMENT", "prod")
    config_dir = Path(__file__).parent
    config_path = config_dir / f"{env}.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. "
            f"Create {env}.json in infra/cdk/config/"
        )

    with open(config_path) as f:
        data = json.load(f)

    # Validate required fields
    required = ["aws_account_id", "aws_region", "ssh_key_name"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Missing required config fields: {missing}")

    return ArchiveConfig(env=env, **data)


if __name__ == "__main__":
    # Quick test
    import sys

    env = sys.argv[1] if len(sys.argv) > 1 else "prod"
    config = load_config(env)
    print(f"Environment: {config.env}")
    print(f"Resource prefix: {config.resource_prefix}")
    print(f"Domain: {config.domain}")
    print(f"Bucket: {config.bucket_name}")
