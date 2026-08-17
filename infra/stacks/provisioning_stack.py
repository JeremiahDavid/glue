from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack, Tags
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct

from meshflow.provisioning import provisioning_project_name


class ProvisioningStack(Stack):
    """CodeBuild project that runs scoped cdk deploy for client onboarding."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env = environment.strip().lower()
        Tags.of(self).add("Environment", env)
        Tags.of(self).add("Application", "meshflow")

        project_root = Path(__file__).resolve().parents[2]
        buildspec_path = project_root / "infra" / "provisioning" / "buildspec.yml"

        role = iam.Role(
            self,
            "ProvisionerRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            description=f"Meshflow client provisioning CodeBuild role ({env})",
        )
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )

        log_group = logs.LogGroup(
            self,
            "ProvisionerLogs",
            log_group_name=f"/meshflow/provisioning/{env}",
            retention=logs.RetentionDays.ONE_MONTH,
        )

        project_name = provisioning_project_name(env)
        self.project = codebuild.Project(
            self,
            "ClientProvisioner",
            project_name=project_name,
            role=role,
            timeout=Duration.hours(2),
            queued_timeout=Duration.minutes(30),
            build_spec=codebuild.BuildSpec.from_asset(str(buildspec_path)),
            source=codebuild.Source.git_hub(
                owner=str(self.node.try_get_context("meshflowGithubOwner") or "hive-flow-ai"),
                repo=str(self.node.try_get_context("meshflowGithubRepo") or "meshflow"),
                webhook=False,
            ),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=True,
                compute_type=codebuild.ComputeType.LARGE,
            ),
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(log_group=log_group, enabled=True),
            ),
            description=f"Deploy ingest/DNA/reporting stacks for new Meshflow clients ({env})",
        )

        CfnOutput(self, "ProvisioningProjectName", value=project_name)
        CfnOutput(self, "ProvisioningProjectArn", value=self.project.project_arn)
