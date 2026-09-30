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
        default=None,
        help="Optional path to service account credentials JSON file. If not set, uses Service Account Impersonation.",
    )
    parser.add_argument(
        "--target-sa",
        default=None,
        help="Target Service Account email to impersonate (defaults to spanner-fgac-readwrite@<project>.iam.gserviceaccount.com)",
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

    if not os.path.exists(args.csv_file):
        print(f"Error: CSV file not found at: {args.csv_file}")
        print("Please run `python3 scripts/generate_data.py` first.")
        sys.exit(1)

    # Disable Spanner built-in metrics exporter to prevent unnecessary Cloud Monitoring calls
    os.environ["SPANNER_DISABLE_BUILTIN_METRICS"] = "true"

    if args.credentials and os.path.exists(args.credentials):
        print(f"Using local key file: {args.credentials}")
        credentials = service_account.Credentials.from_service_account_file(args.credentials)
        project = args.project or credentials.project_id
        client = spanner.Client(project=project, credentials=credentials, disable_builtin_metrics=True)
    else:
        project = args.project or def_proj or "mague-tf"
        target_sa = args.target_sa or f"spanner-fgac-readwrite@{project}.iam.gserviceaccount.com"
        print(f"Using Service Account Impersonation: {target_sa}")
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from scripts.auth import get_impersonated_client
        client = get_impersonated_client(target_sa_email=target_sa, project_id=project)

    print(f"Connecting to Spanner:")
    print(f"  Project:  {project}")
    print(f"  Instance: {args.instance}")
    print(f"  Database: {args.database}")
    print(f"  Database Role: readwrite")

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
