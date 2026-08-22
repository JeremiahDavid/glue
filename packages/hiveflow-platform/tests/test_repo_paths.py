from pathlib import Path

from hiveflow.repo_paths import find_project_root


def test_find_project_root_monorepo_layout() -> None:
    root = find_project_root()
    assert (root / "config.yaml").is_file()
    assert (root / "packages").is_dir()


def test_find_project_root_lambda_bundle_layout(tmp_path: Path) -> None:
    find_project_root.cache_clear()
    bundle = tmp_path / "lambda"
    (bundle / "hiveflow").mkdir(parents=True)
    (bundle / "config.yaml").write_text("companies: {}\n", encoding="utf-8")
    module = bundle / "hiveflow" / "repo_paths.py"
    module.write_text('"""stub"""\n', encoding="utf-8")

    assert find_project_root(module) == bundle

    find_project_root.cache_clear()
