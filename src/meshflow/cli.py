from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meshflow.config import load_qbo_settings
from meshflow.project_config import DEFAULT_CONFIG_PATH, resolve_qbo_ingest_entities
from meshflow.qbo.client import QBOClient
from meshflow.qbo.ingest import ingest_all, ingest_single
from meshflow.qbo.oauth import connect_quickbooks
from meshflow.secrets_manager import create_qbo_secrets_from_yaml


def create_secrets_main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Meshflow QBO secrets in AWS Secrets Manager from a YAML file"
    )
    parser.add_argument(
        "--file",
        required=True,
        help="YAML file describing one or more QBO secrets to create",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Project config.yaml used to resolve secret names and regions (default: config.yaml)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update existing secrets with values from the YAML file",
    )
    args = parser.parse_args()

    secrets_path = Path(args.file)
    if not secrets_path.is_file():
        raise FileNotFoundError(f"Secrets file not found: {secrets_path}")

    config_path = Path(args.config)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    created, existing, updated = create_qbo_secrets_from_yaml(
        secrets_path,
        config_path=config_path,
        update_existing=args.update,
    )
    print(f"Done. Created {created}, already existed {existing}, updated {updated}.")


def auth_main() -> None:
    settings = load_qbo_settings()
    tokens = connect_quickbooks(settings)
    print("QuickBooks connected.")
    print(f"  Company realm ID: {tokens.realm_id}")
    print(f"  Tokens saved to:  AWS secret {settings.secret_id}")


def ingest_main() -> None:
    parser = argparse.ArgumentParser(description="Ingest raw entities from QuickBooks Online")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Project config.yaml used to resolve entity bundle (default: config.yaml)",
    )
    parser.add_argument(
        "--entity",
        help="Ingest a single entity instead of the configured bundle",
    )
    args = parser.parse_args()

    entity_bundle, entities = resolve_qbo_ingest_entities(path=Path(args.config))
    if args.entity and args.entity not in entities:
        available = ", ".join(sorted(entities))
        parser.error(f"Unknown entity {args.entity!r} for bundle {entity_bundle!r}. Available: {available}")

    settings = load_qbo_settings()
    client = QBOClient.from_saved_tokens(settings)

    if args.entity:
        import json

        result = ingest_single(client, settings, args.entity, entities=entities)
        print(json.dumps(result, indent=2))
        return

    manifest = ingest_all(
        client,
        settings,
        entities=entities,
        entity_bundle=entity_bundle,
    )
    print("QuickBooks ingest complete.")
    print(f"  Bundle: {entity_bundle}")
    print(f"  Company: {manifest.get('company_name')}")
    print(f"  Manifest: {manifest['manifest_path']}")
    for entity in manifest["entities"]:
        print(f"  - {entity['entity']}: {entity['row_count']} rows -> {entity['path']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ingest":
        sys.argv.pop(1)
        ingest_main()
    else:
        auth_main()
