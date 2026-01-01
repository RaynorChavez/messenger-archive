"""EC2 compute stack for Messenger Archive."""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
)
from constructs import Construct

from config.base import ArchiveConfig


class ComputeStack(cdk.Stack):
    """Stack for EC2 instance, security group, and Elastic IP."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: ArchiveConfig,
        backup_bucket: s3.Bucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Default VPC
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        # Security Group - only SSH (22), HTTP (80), HTTPS (443)
        security_group = ec2.SecurityGroup(
            self,
            "SecurityGroup",
            vpc=vpc,
            description="Messenger Archive - SSH, HTTP, HTTPS only",
            security_group_name=f"{config.resource_prefix}-sg",
            allow_all_outbound=True,
        )

        # SSH - consider restricting to your IP in production
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(22),
            "SSH access",
        )

        # HTTP (for Caddy ACME challenge)
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "HTTP for ACME",
        )

        # HTTPS
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            "HTTPS access",
        )

        # IAM Role for EC2 (S3 backup access)
        role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            role_name=f"{config.resource_prefix}-instance-role",
        )

        # Grant S3 access for backups
        backup_bucket.grant_read_write(role)

        # User data script - runs on first boot
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "#!/bin/bash",
            "set -e",
            "",
            "# Log everything",
            "exec > >(tee /var/log/user-data.log) 2>&1",
            "",
            "echo '=== Updating system ==='",
            "apt-get update",
            "apt-get upgrade -y",
            "",
            "echo '=== Installing Docker ==='",
            "curl -fsSL https://get.docker.com | sh",
            "usermod -aG docker ubuntu",
            "",
            "echo '=== Installing fail2ban ==='",
            "apt-get install -y fail2ban",
            "systemctl enable fail2ban",
            "systemctl start fail2ban",
            "",
            "echo '=== Setting up swap (2GB) ==='",
            "fallocate -l 2G /swapfile",
            "chmod 600 /swapfile",
            "mkswap /swapfile",
            "swapon /swapfile",
            "echo '/swapfile none swap sw 0 0' >> /etc/fstab",
            "echo 'vm.swappiness=10' >> /etc/sysctl.conf",
            "sysctl -p",
            "",
            "echo '=== Hardening SSH ==='",
            "sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config",
            "sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config",
            "systemctl restart sshd",
            "",
            "echo '=== Creating app directory ==='",
            "mkdir -p /opt/messenger-archive",
            "chown ubuntu:ubuntu /opt/messenger-archive",
            "",
            "echo '=== Installing AWS CLI ==='",
            "apt-get install -y awscli",
            "",
            "echo '=== User data complete ==='",
        )

        # EC2 Instance
        instance = ec2.Instance(
            self,
            "Instance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MICRO,
            ),
            machine_image=ec2.MachineImage.lookup(
                name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*",
                owners=["099720109477"],  # Canonical
            ),
            vpc=vpc,
            security_group=security_group,
            key_name=config.ssh_key_name,
            role=role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/sda1",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
        )

        # Tag the instance
        cdk.Tags.of(instance).add("Name", config.resource_prefix)

        # Elastic IP
        eip = ec2.CfnEIP(self, "ElasticIP", domain="vpc")

        # Associate EIP with instance
        ec2.CfnEIPAssociation(
            self,
            "EIPAssociation",
            eip=eip.ref,
            instance_id=instance.instance_id,
        )

        # Outputs
        cdk.CfnOutput(
            self,
            "InstanceId",
            value=instance.instance_id,
            description="EC2 Instance ID",
        )

        cdk.CfnOutput(
            self,
            "PublicIP",
            value=eip.ref,
            description="Elastic IP address - point your DuckDNS domain here",
        )

        cdk.CfnOutput(
            self,
            "SSHCommand",
            value=f"ssh ubuntu@{eip.ref}",
            description="SSH command to connect",
        )

        # Store for reference
        self.instance = instance
        self.elastic_ip = eip
        self.security_group = security_group
