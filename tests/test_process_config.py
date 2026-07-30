import pytest

from meshflow.process_config import (
    Process,
    get_process,
    lambda_name_for_process,
    list_process_keys,
    load_process_config,
    resolve_process_connector,
    step_function_name_for_process,
)
from meshflow.project_config import lambda_function_name, meshflow_resource_name, step_function_name


def test_process_config_loads_all_deployed_processes() -> None:
    keys = list_process_keys()
    assert keys == ["consolidate", "fanout", "finalize", "ingest", "prepare"]


def test_get_process_ingest_metadata() -> None:
    process = get_process(Process.INGEST)
    assert process.stage == "bronze"
    assert process.slug == "ingest"
    assert process.resource == "lambda"
    assert "dbc" in process.connectors


def test_lambda_name_for_process_uses_yaml_slug() -> None:
    assert (
        lambda_name_for_process("POC", "dev", "dbc", Process.INGEST)
        == "poc-dev-dbc-bronze-ingest"
    )


def test_step_function_name_for_process_uses_yaml_slug() -> None:
    assert (
        step_function_name_for_process("POC", "dev", "qbo", Process.FANOUT)
        == "poc-dev-qbo-bronze-fanout"
    )


def test_shared_silver_consolidate_uses_all_connector() -> None:
    assert resolve_process_connector("qbo", Process.CONSOLIDATE) == "all"
    assert (
        lambda_name_for_process("POC", "dev", "qbo", Process.CONSOLIDATE)
        == "poc-dev-all-silver-consolidate"
    )


def test_qbd_bronze_ingest_name() -> None:
    assert (
        lambda_name_for_process("POC", "dev", "qbd", Process.INGEST)
        == "poc-dev-qbd-bronze-ingest"
    )


def test_unknown_process_raises() -> None:
    with pytest.raises(ValueError, match="Unknown process"):
        get_process("not-a-process")


def test_wrong_resource_type_raises() -> None:
    with pytest.raises(ValueError, match="not a Lambda resource"):
        lambda_name_for_process("POC", "dev", "qbo", Process.FANOUT)


def test_low_level_name_helpers_still_work() -> None:
    assert lambda_function_name("POC", "dev", "dbc", "bronze", "ingest") == "poc-dev-dbc-bronze-ingest"
    assert step_function_name("POC", "dev", "qbo", "bronze", "fanout") == "poc-dev-qbo-bronze-fanout"


def test_meshflow_resource_name_rejects_overlong_names() -> None:
    with pytest.raises(ValueError, match="exceeds 64 characters"):
        meshflow_resource_name("a" * 40, "dev", "connector", "bronze", "process", max_length=64)


def test_process_config_has_stage_descriptions() -> None:
    payload = load_process_config()
    stages = payload["stages"]
    assert "bronze" in stages
    assert "silver" in stages
    assert "gold" in stages
