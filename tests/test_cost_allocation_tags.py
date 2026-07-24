from meshflow.project_config import aws_tag_list, cost_allocation_tags


def test_cost_allocation_tags_include_company() -> None:
    tags = cost_allocation_tags("POC", "dev")
    assert tags["Company"] == "POC"
    assert tags["Environment"] == "dev"
    assert tags["Application"] == "meshflow"


def test_aws_tag_list_format() -> None:
    tags = aws_tag_list(cost_allocation_tags("ACME", "prod"))
    assert {"Key": "Company", "Value": "ACME"} in tags
