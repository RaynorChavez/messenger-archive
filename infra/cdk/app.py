#!/usr/bin/env python3
"""CDK app entry point for Messenger Archive infrastructure."""

import aws_cdk as cdk

from config.base import load_config
from stacks.storage_stack import StorageStack
from stacks.compute_stack import ComputeStack


def main() -> None:
    """Create the CDK app and stacks."""
    app = cdk.App()

    # Load configuration
    config = load_config()

    # Environment
    env = cdk.Environment(
        account=config.aws_account_id,
        region=config.aws_region,
    )

    # Stack naming
    prefix = config.resource_prefix

    # Create stacks
    storage_stack = StorageStack(
        app,
        f"{prefix}-storage",
        config=config,
        env=env,
        description="Messenger Archive S3 backup bucket",
    )

    compute_stack = ComputeStack(
        app,
        f"{prefix}-compute",
        config=config,
        backup_bucket=storage_stack.backup_bucket,
        env=env,
        description="Messenger Archive EC2 instance",
    )

    # Dependencies
    compute_stack.add_dependency(storage_stack)

    # Synthesize
    app.synth()


if __name__ == "__main__":
    main()
