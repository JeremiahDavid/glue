from meshflow.dna.web.domain_names import dns_record_name, expand_hostnames


def test_record_name_for_apex_and_subdomain() -> None:
    zone = "hive-flow-ai.com"
    assert dns_record_name("hive-flow-ai.com", zone) is None
    assert dns_record_name("www.hive-flow-ai.com", zone) == "www"
    assert dns_record_name("app.hive-flow-ai.com", zone) == "app"


def test_expand_hostnames() -> None:
    hostnames = expand_hostnames(
        zone_name="hive-flow-ai.com",
        primary_hostname="hive-flow-ai.com",
        alternate_hostnames=["www", "app.hive-flow-ai.com"],
    )
    assert hostnames == [
        "hive-flow-ai.com",
        "www.hive-flow-ai.com",
        "app.hive-flow-ai.com",
    ]
