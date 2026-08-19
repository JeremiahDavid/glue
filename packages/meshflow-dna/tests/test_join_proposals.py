"""DNA join proposals from grain and keys."""

from __future__ import annotations

from meshflow.dna.join_proposals import JoinCatalog, JoinTarget, propose_joins_from_catalog, source_keys


def _table() -> dict:
    return {
        "entity_name": "price_list",
        "grain": "one row per item",
        "schema": [
            {"name": "item_no", "type": "string", "is_key": True},
            {"name": "unit_price", "type": "number"},
        ],
    }


def test_source_keys_prefer_schema_flags() -> None:
    assert source_keys(_table()) == ["item_no"]


def test_proposes_silver_join_on_grain_and_key_stem() -> None:
    catalog = JoinCatalog(
        targets=[
            JoinTarget(
                layer="silver",
                name="items",
                source="dbc",
                primary_key="id",
                grain="item",
                columns=["id", "number", "displayName"],
                pack_entity_id="ent_items",
            ),
            JoinTarget(
                layer="silver",
                name="customers",
                source="dbc",
                primary_key="id",
                grain="customer",
                columns=["id", "displayName"],
                pack_entity_id="ent_customers",
            ),
        ],
        pack_joins=[
            {
                "id": "join_invoice_line_item",
                "left_entity": "ent_sales_invoice_lines",
                "right_entity": "ent_items",
                "left_key": "itemId",
                "right_key": "id",
                "cardinality": "many_to_one",
            },
        ],
    )
    catalog.targets.append(
        JoinTarget(
            layer="silver",
            name="sales_invoice_lines",
            source="dbc",
            primary_key="id",
            grain="line",
            columns=["id", "itemId", "documentId"],
            pack_entity_id="ent_sales_invoice_lines",
        )
    )
    payload = propose_joins_from_catalog(_table(), catalog)
    targets = {item["target"]: item for item in payload["proposals"]}
    assert "items" in targets
    assert targets["items"]["left_key"] == "item_no"
    assert targets["items"]["right_key"] == "id"
    assert targets["items"]["layer"] == "silver"
    assert "sales_invoice_lines" in targets
    assert targets["sales_invoice_lines"]["via_pack_join"] == "join_invoice_line_item"


def test_proposes_gold_join_from_grain_columns() -> None:
    catalog = JoinCatalog(
        targets=[
            JoinTarget(
                layer="gold",
                name="fact_item_margin",
                source="dna",
                grain="gold",
                grain_columns=["itemId", "period_key"],
                columns=["itemId", "period_key", "margin"],
            )
        ]
    )
    payload = propose_joins_from_catalog(_table(), catalog)
    assert len(payload["proposals"]) == 1
    proposal = payload["proposals"][0]
    assert proposal["layer"] == "gold"
    assert proposal["target"] == "fact_item_margin"
    assert proposal["left_key"] == "item_no"
    assert proposal["right_key"] == "itemId"
