from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import jsii
from aws_cdk import BundlingOptions, ILocalBundling, aws_lambda as _lambda

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@jsii.implements(ILocalBundling)
class LocalPythonBundling:
    """Bundle Lambda deps with local pip when Docker is unavailable."""

    def try_bundle(self, output_dir: str, _options: BundlingOptions) -> bool:
        pip_platform = "manylinux2014_x86_64"
        pip_python = "3.12"
        common = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-t",
            output_dir,
            "--platform",
            pip_platform,
            "--python-version",
            pip_python,
            "--only-binary=:all:",
        ]
        try:
            subprocess.run(
                [*common, "-r", str(PROJECT_ROOT / "requirements.txt")],
                check=True,
                capture_output=True,
            )
            shutil.copytree(
                PROJECT_ROOT / "src" / "meshflow",
                Path(output_dir) / "meshflow",
                dirs_exist_ok=True,
            )
            shutil.copy2(PROJECT_ROOT / "config.yaml", Path(output_dir) / "config.yaml")
            process_config = PROJECT_ROOT / "process_config.yaml"
            if process_config.exists():
                shutil.copy2(process_config, Path(output_dir) / "process_config.yaml")
        except (subprocess.CalledProcessError, OSError):
            return False
        return True


def meshflow_lambda_code() -> _lambda.Code:
    return _lambda.Code.from_asset(
        str(PROJECT_ROOT),
        bundling=BundlingOptions(
            image=_lambda.Runtime.PYTHON_3_12.bundling_image,
            command=[
                "bash",
                "-c",
                "pip install -r /asset-input/requirements.txt -t /asset-output && "
                "pip install /asset-input -t /asset-output --no-deps && "
                "cp /asset-input/config.yaml /asset-output/config.yaml && "
                "cp /asset-input/process_config.yaml /asset-output/process_config.yaml",
            ],
            local=LocalPythonBundling(),
        ),
    )
