#!/usr/bin/env python3
"""
Seeds data/customers.csv into Cloud Spanner using the Full database user credentials.
"""

import argparse
import csv
import json
import os
import sys
from google.cloud import spanner
from google.oauth2 import service_account

def get_default_config():
    """Attempts to read defaults from terraform.tfstate or terraform.tfvars."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tfstate_path = os.path.join(base_dir, "terraform", "terraform.tfstate")
    project_id, instance_id, database_id = None, "shared-demos", "fgac-demo"

    if os.path.exists(tfstate_path):
        try:
            with open(tfstate_path) as f:
                state = json.load(f)
                outputs = state.get("outputs", {})
                if "project_id" in outputs:
                    project_id = outputs["project_id"]["value"]
                if "instance_name" in outputs:
                    instance_id = outputs["instance_name"]["value"]
                if "database_name" in outputs:
                    database_id = outputs["database_name"]["value"]
        except Exception:
            pass

    return project_id, instance_id, database_id

def main():
    parser = argparse.ArgumentParser(description="Seed Cloud Spanner table with customer data")
    def_proj, def_inst, def_db = get_default_config()

    parser.add_argument("--project", default=def_proj, help="Google Cloud Project ID")
    parser.add_argument("--instance", default=def_inst, help="Spanner Instance Name")
    parser.add_argument("--database", default=def_db, help="Spanner Database Name")
    parser.add_argument(
        "--credentials",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "credentials",
            "readwrite_credentials.json",
        ),
        help="Path to service account credentials JSON file (defaults to readwrite_credentials.json)",
    )
    parser.add_argument(
        "--csv-file",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "customers.csv",
        ),
        help="Path to CSV file with customer data",
    )
    args = parser.parse_args()

    if not os.path.exists(args.credentials):
        print(f"Error: Credential file not found at: {args.credentials}")
        print("Please run `terraform apply` first to generate the credentials.")
        sys.exit(1)

    if not os.path.exists(args.csv_file):
        print(f"Error: CSV file not found at: {args.csv_file}")
        print("Please run `python3 scripts/generate_data.py` first.")
        sys.exit(1)

    # Load credentials
    credentials = service_account.Credentials.from_service_account_file(args.credentials)
    project = args.project or credentials.project_id

    print(f"Connecting to Spanner:")
    print(f"  Project:  {project}")
    print(f"  Instance: {args.instance}")
    print(f"  Database: {args.database}")
    print(f"  Using:    {os.path.basename(args.credentials)} (role: readwrite)")

    # Disable Spanner built-in metrics exporter to prevent unnecessary Cloud Monitoring calls
    os.environ["SPANNER_DISABLE_BUILTIN_METRICS"] = "true"

    client = spanner.Client(
        project=project,
        credentials=credentials,
        disable_builtin_metrics=True,
    )
    instance = client.instance(args.instance)
    database = instance.database(args.database, database_role="readwrite")

    # Read records from CSV
    columns = ["id", "first_name", "last_name", "ssn", "email", "phone_number"]
    rows = []
    with open(args.csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append([r[col] for col in columns])

    print(f"\nInserting {len(rows)} rows into table 'customers'...")
    # Cloud Spanner batch insert
    with database.batch() as batch:
        batch.insert_or_update(
            table="customers",
            columns=columns,
            values=rows,
        )

    print(f"Successfully seeded {len(rows)} records into Spanner table 'customers'!")

if __name__ == "__main__":
    main()
