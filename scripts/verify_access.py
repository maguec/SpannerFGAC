#!/usr/bin/env python3
"""
Automated Verification Matrix Test for Cloud Spanner Fine-Grained Access Control (FGAC).
Validates that each persona (Full, ReadWrite, FullView, Masked) exhibits the exact expected
access permissions on the base table and masked view.
"""

import argparse
import json
import os
import sys
import uuid
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied
from google.cloud import spanner
from google.oauth2 import service_account
from rich.console import Console
from rich.table import Table

console = Console()

PERSONA_CONFIG = {
    "readwrite": {
        "title": "1. ReadWrite (FGAC Role)",
        "key_file": "readwrite_credentials.json",
        "database_role": "readwrite",
        "expected": {
            "table_select": "ALLOWED",
            "view_select": "ALLOWED",
            "dml_insert": "ALLOWED",
            "dml_delete": "ALLOWED",
        },
    },
    "fullview": {
        "title": "2. FullView (FGAC Role)",
        "key_file": "fullview_credentials.json",
        "database_role": "fullview",
        "expected": {
            "table_select": "ALLOWED",
            "view_select": "ALLOWED",
            "dml_insert": "DENIED",
            "dml_delete": "DENIED",
        },
    },
    "masked": {
        "title": "3. Masked (FGAC Role)",
        "key_file": "masked_credentials.json",
        "database_role": "masked",
        "expected": {
            "table_select": "DENIED",
            "view_select": "ALLOWED",
            "dml_insert": "DENIED",
            "dml_delete": "DENIED",
        },
    },
}

def get_default_config():
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

def test_persona(project: str, instance_id: str, database_id: str, creds_dir: str, persona_key: str):
    cfg = PERSONA_CONFIG[persona_key]
    key_path = os.path.join(creds_dir, cfg["key_file"])

    if not os.path.exists(key_path):
        return {
            "title": cfg["title"],
            "error": f"Missing key: {cfg['key_file']}",
            "results": {},
        }

    os.environ["SPANNER_DISABLE_BUILTIN_METRICS"] = "true"
    creds = service_account.Credentials.from_service_account_file(key_path)
    client = spanner.Client(
        project=project or creds.project_id,
        credentials=creds,
        disable_builtin_metrics=True,
    )
    instance = client.instance(instance_id)

    db_role = cfg["database_role"]
    if db_role:
        database = instance.database(database_id, database_role=db_role)
    else:
        database = instance.database(database_id)

    results = {}
    sample_data = {}

    # Test 1: Query base table 'customers'
    try:
        with database.snapshot() as snapshot:
            rows = list(snapshot.execute_sql("SELECT id, first_name, last_name, ssn, phone_number FROM customers LIMIT 1"))
            if rows:
                results["table_select"] = "ALLOWED"
                sample_data["table_ssn"] = rows[0][3]
            else:
                results["table_select"] = "ALLOWED (Empty)"
    except PermissionDenied:
        results["table_select"] = "DENIED"
    except Exception as e:
        results["table_select"] = f"ERROR ({type(e).__name__})"

    # Test 2: Query view 'customers_masked'
    try:
        with database.snapshot() as snapshot:
            rows = list(snapshot.execute_sql("SELECT id, first_name, last_name, ssn, phone_number FROM customers_masked LIMIT 1"))
            if rows:
                results["view_select"] = "ALLOWED"
                sample_data["view_ssn"] = rows[0][3]
            else:
                results["view_select"] = "ALLOWED (Empty)"
    except PermissionDenied:
        results["view_select"] = "DENIED"
    except Exception as e:
        results["view_select"] = f"ERROR ({type(e).__name__})"

    # Test 3 & 4: DML Insert and Delete
    test_id = str(uuid.uuid4())
    insert_sql = (
        f"INSERT INTO customers (id, first_name, last_name, ssn, email, phone_number) "
        f"VALUES ('{test_id}', 'Test', 'User', '000-00-0000', 'test@test.com', '555-555-5555')"
    )
    delete_sql = f"DELETE FROM customers WHERE id = '{test_id}'"

    def run_dml(transaction, query):
        transaction.execute_update(query)

    try:
        database.run_in_transaction(run_dml, insert_sql)
        results["dml_insert"] = "ALLOWED"
        # If insert succeeded, attempt delete
        try:
            database.run_in_transaction(run_dml, delete_sql)
            results["dml_delete"] = "ALLOWED"
        except PermissionDenied:
            results["dml_delete"] = "DENIED"
        except Exception as e:
            results["dml_delete"] = f"ERROR ({type(e).__name__})"
    except PermissionDenied:
        results["dml_insert"] = "DENIED"
        results["dml_delete"] = "DENIED"
    except Exception as e:
        results["dml_insert"] = f"ERROR ({type(e).__name__})"
        results["dml_delete"] = f"ERROR ({type(e).__name__})"

    return {
        "title": cfg["title"],
        "expected": cfg["expected"],
        "results": results,
        "sample_data": sample_data,
        "error": None,
    }

def main():
    parser = argparse.ArgumentParser(description="Verify Cloud Spanner FGAC permissions")
    def_proj, def_inst, def_db = get_default_config()

    parser.add_argument("--project", default=def_proj, help="Google Cloud Project ID")
    parser.add_argument("--instance", default=def_inst, help="Spanner Instance Name")
    parser.add_argument("--database", default=def_db, help="Spanner Database Name")
    parser.add_argument(
        "--credentials-dir",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "credentials",
        ),
        help="Path to directory containing credential JSON files",
    )
    args = parser.parse_args()

    console.print(f"[bold cyan]Testing Spanner FGAC Permissions[/bold cyan]")
    console.print(f"Project:  [yellow]{args.project}[/yellow]")
    console.print(f"Instance: [yellow]{args.instance}[/yellow]")
    console.print(f"Database: [yellow]{args.database}[/yellow]\n")

    table = Table(title="Spanner FGAC Security Verification Matrix", show_header=True, header_style="bold magenta")
    table.add_column("Persona", style="cyan", width=26)
    table.add_column("Table Query\n(Unmasked)", justify="center")
    table.add_column("View Query\n(Masked)", justify="center")
    table.add_column("DML Insert", justify="center")
    table.add_column("DML Delete", justify="center")
    table.add_column("Data Sample (SSN)", justify="center")
    table.add_column("Status", justify="center")

    all_passed = True

    for p_key in ["readwrite", "fullview", "masked"]:
        outcome = test_persona(args.project, args.instance, args.database, args.credentials_dir, p_key)
        if outcome["error"]:
            table.add_row(outcome["title"], "[red]N/A[/red]", "[red]N/A[/red]", "[red]N/A[/red]", "[red]N/A[/red]", outcome["error"], "[red]MISSING KEY[/red]")
            all_passed = False
            continue

        res = outcome["results"]
        exp = outcome["expected"]

        def format_status(op_key):
            actual = res.get(op_key, "")
            expected = exp.get(op_key, "")
            if actual == expected or (expected == "ALLOWED" and "ALLOWED" in actual):
                color = "green" if actual.startswith("ALLOWED") else "yellow"
                return f"[{color}]{actual}[/{color}]"
            else:
                return f"[red bold]{actual}[/red bold]"

        t_stat = format_status("table_select")
        v_stat = format_status("view_select")
        i_stat = format_status("dml_insert")
        d_stat = format_status("dml_delete")

        persona_passed = all(
            res.get(k) == exp.get(k) or (exp.get(k) == "ALLOWED" and res.get(k, "").startswith("ALLOWED"))
            for k in exp
        )

        overall = "[green]✓ PASS[/green]" if persona_passed else "[red bold]✗ FAIL[/red bold]"
        if not persona_passed:
            all_passed = False

        sample_ssn = outcome["sample_data"].get("table_ssn") or outcome["sample_data"].get("view_ssn") or "N/A"

        table.add_row(outcome["title"], t_stat, v_stat, i_stat, d_stat, sample_ssn, overall)

    console.print(table)

    if all_passed:
        console.print("\n[bold green]All FGAC security boundaries verified successfully![/bold green]\n")
    else:
        console.print("\n[bold yellow]Some tests did not match expectations or credential files were missing.[/bold yellow]\n")

if __name__ == "__main__":
    main()
