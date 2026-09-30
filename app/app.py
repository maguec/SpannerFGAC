#!/usr/bin/env python3
"""
Interactive Cloud Spanner FGAC Demo Dashboard built with NiceGUI.
Enforces tech stack constraints per demotech skill guidelines.
"""

import json
import os
import subprocess
import uuid
from google.api_core.exceptions import PermissionDenied
from google.cloud import spanner
from google.oauth2 import service_account
from nicegui import ui

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS_DIR = os.path.join(BASE_DIR, "credentials")
TFSTATE_PATH = os.path.join(BASE_DIR, "terraform", "terraform.tfstate")

def get_config():
    project_id, instance_id, database_id = "mague-tf", "shared-demos", "fgac-demo"
    if os.path.exists(TFSTATE_PATH):
        try:
            with open(TFSTATE_PATH) as f:
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

DEFAULT_PROJECT, DEFAULT_INSTANCE, DEFAULT_DATABASE = get_config()

PERSONAS = {
    "ReadWrite (IAM Role)": {
        "key_file": "readwrite_credentials.json",
        "database_role": "readwrite",
        "iam_role": "roles/spanner.databaseRoleUser",
        "description": "IAM Service Account authorized to assume the 'readwrite' database role (SELECT, INSERT, UPDATE, DELETE).",
        "expected_table": "Allowed (Unmasked PII)",
        "expected_view": "Allowed (Masked PII)",
        "expected_dml": "Allowed",
        "color": "blue",
    },
    "FullView (IAM Role)": {
        "key_file": "fullview_credentials.json",
        "database_role": "fullview",
        "iam_role": "roles/spanner.databaseRoleUser",
        "description": "IAM Service Account authorized to assume the 'fullview' database role (read-only unmasked SELECT).",
        "expected_table": "Allowed (Unmasked PII)",
        "expected_view": "Allowed (Masked PII)",
        "expected_dml": "Denied (403)",
        "color": "purple",
    },
    "Masked (IAM Role)": {
        "key_file": "masked_credentials.json",
        "database_role": "masked",
        "iam_role": "roles/spanner.databaseRoleUser",
        "description": "IAM Service Account authorized to assume the 'masked' database role (SELECT on masked view only).",
        "expected_table": "Denied (403 Permission Denied)",
        "expected_view": "Allowed (Masked PII Only)",
        "expected_dml": "Denied (403)",
        "color": "orange",
    },
}

STATIC_DDL = {
    "table": """CREATE TABLE customers (
  id STRING(36) NOT NULL,
  first_name STRING(64) NOT NULL,
  last_name STRING(64) NOT NULL,
  ssn STRING(11) NOT NULL,
  email STRING(128) NOT NULL,
  phone_number STRING(32) NOT NULL,
) PRIMARY KEY(id);""",
    "view": """CREATE VIEW customers_masked SQL SECURITY DEFINER AS
SELECT
  customers.id,
  customers.first_name,
  customers.last_name,
  CONCAT('XXX-XX-', SUBSTR(customers.ssn, -4)) AS ssn,
  customers.email,
  CONCAT('XXX-XXX-', SUBSTR(customers.phone_number, -4)) AS phone_number
FROM customers;""",
    "roles": """-- 1. Create Database Roles
CREATE ROLE readwrite;
CREATE ROLE fullview;
CREATE ROLE masked;

-- 2. ReadWrite Role: Full read/write on base table and view
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE customers TO ROLE readwrite;
GRANT SELECT ON VIEW customers_masked TO ROLE readwrite;

-- 3. FullView Role: Read-only on base table (unmasked) and view
GRANT SELECT ON TABLE customers TO ROLE fullview;
GRANT SELECT ON VIEW customers_masked TO ROLE fullview;

-- 4. Masked Role: Read-only ONLY on masked view (NO table access)
GRANT SELECT ON VIEW customers_masked TO ROLE masked;""",
}

def fetch_live_ddl():
    try:
        cmd = [
            "gcloud", "spanner", "databases", "ddl", "describe",
            DEFAULT_DATABASE,
            f"--instance={DEFAULT_INSTANCE}",
            f"--project={DEFAULT_PROJECT}",
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8")
        if out.strip():
            return out.strip()
    except Exception:
        pass

    # Fallback to combined static DDL
    return f"{STATIC_DDL['table']}\n\n{STATIC_DDL['view']}\n\n{STATIC_DDL['roles']}"

def get_spanner_db(persona_name: str):
    info = PERSONAS[persona_name]
    role = info["database_role"]
    target_sa = f"spanner-fgac-{role}@{DEFAULT_PROJECT}.iam.gserviceaccount.com"
    key_path = os.path.join(CREDS_DIR, info["key_file"])

    os.environ["SPANNER_DISABLE_BUILTIN_METRICS"] = "true"

    if os.path.exists(key_path):
        creds = service_account.Credentials.from_service_account_file(key_path)
        client = spanner.Client(
            project=DEFAULT_PROJECT or creds.project_id,
            credentials=creds,
            disable_builtin_metrics=True,
        )
        sa_email = creds.service_account_email
    else:
        # Default to Service Account Impersonation
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from scripts.auth import get_impersonated_client
        client = get_impersonated_client(target_sa_email=target_sa, project_id=DEFAULT_PROJECT)
        sa_email = f"{target_sa} (impersonated)"

    instance = client.instance(DEFAULT_INSTANCE)
    if role:
        return instance.database(DEFAULT_DATABASE, database_role=role), sa_email
    return instance.database(DEFAULT_DATABASE), sa_email

@ui.page("/")
def index():
    ui.colors(primary="#1976D2", secondary="#26A69A", accent="#9C27B0")

    with ui.header().classes("items-center justify-between bg-slate-900 text-white p-4 shadow"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("security", size="2rem").classes("text-blue-400")
            ui.label("Cloud Spanner Fine-Grained Access Control (FGAC)").classes("text-xl font-bold")
        with ui.row().classes("items-center gap-4 text-xs text-slate-300"):
            ui.label(f"Project: {DEFAULT_PROJECT}").classes("bg-slate-800 px-3 py-1 rounded")
            ui.label(f"Instance: {DEFAULT_INSTANCE}").classes("bg-slate-800 px-3 py-1 rounded")
            ui.label(f"Database: {DEFAULT_DATABASE}").classes("bg-slate-800 px-3 py-1 rounded")

    with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-6"):

        # Top Tabs Navigation
        with ui.tabs().classes("w-full bg-slate-100 rounded-lg p-1 text-slate-700 shadow-sm") as tabs:
            tab_demo = ui.tab("Security & Access Demo", icon="shield")
            tab_ddl = ui.tab("Database DDL & Schema", icon="code")
            tab_conn = ui.tab("Python Connection & Role Usage", icon="terminal")

        with ui.tab_panels(tabs, value=tab_demo).classes("w-full bg-transparent p-0"):

            # -----------------------------------------------------------------------------------------
            # TAB 1: INTERACTIVE SECURITY DEMO
            # -----------------------------------------------------------------------------------------
            with ui.tab_panel(tab_demo).classes("p-0 gap-6 flex flex-col"):

                # Persona Selection & Details Card
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    ui.label("1. Select Persona / Security Principal").classes("text-lg font-bold text-slate-800")
                    
                    with ui.row().classes("w-full items-center gap-6 mt-2"):
                        selected_persona = ui.select(
                            list(PERSONAS.keys()),
                            value=list(PERSONAS.keys())[0],
                            label="Active Persona",
                        ).classes("w-80")

                    desc_label = ui.label("").classes("text-sm text-slate-600 mt-2")
                    
                    with ui.row().classes("gap-3 mt-3 flex-wrap items-center"):
                        badge_iam = ui.badge("IAM: roles/spanner.databaseRoleUser", color="indigo").classes("text-xs")
                        badge_dbrole = ui.badge("DB Role: -", color="teal").classes("text-xs font-mono")
                        badge_table = ui.badge("Table Access", color="grey").classes("text-xs")
                        badge_view = ui.badge("View Access", color="grey").classes("text-xs")
                        badge_dml = ui.badge("DML Access", color="grey").classes("text-xs")
                        active_sa = ui.label("").classes("text-xs text-slate-400 self-center ml-2")

                    def update_persona_info():
                        p = PERSONAS[selected_persona.value]
                        role = p["database_role"]
                        target_sa = f"spanner-fgac-{role}@{DEFAULT_PROJECT}.iam.gserviceaccount.com"
                        desc_label.text = p["description"]
                        badge_iam.text = f"IAM: {p['iam_role']}"
                        badge_dbrole.text = f"Assumed DB Role: {p['database_role']}"
                        badge_table.text = f"Table: {p['expected_table']}"
                        badge_table.props(f"color={p['color']}")
                        badge_view.text = f"View: {p['expected_view']}"
                        badge_dml.text = f"DML: {p['expected_dml']}"
                        key_path = os.path.join(CREDS_DIR, p["key_file"])
                        if os.path.exists(key_path):
                            with open(key_path) as kf:
                                email = json.load(kf).get("client_email", "")
                                active_sa.text = f"Key: {p['key_file']} ({email})"
                        else:
                            active_sa.text = f"Target Principal: {target_sa} (via Impersonation)"

                    selected_persona.on_value_change(update_persona_info)
                    update_persona_info()

                # Action Buttons Card
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    ui.label("2. Execute Operations with Selected Persona").classes("text-lg font-bold text-slate-800")

                    with ui.row().classes("gap-4 mt-2"):
                        btn_table = ui.button("Query Base Table (customers)", icon="table_rows").props("unelevated color=primary")
                        btn_view = ui.button("Query Masked View (customers_masked)", icon="visibility").props("unelevated color=secondary")
                        btn_insert = ui.button("Attempt Insert Record (DML)", icon="add_circle").props("unelevated color=accent")

                # Response / Audit Log Box
                status_banner = ui.card().classes("w-full p-4 hidden shadow-sm")
                status_text = ui.label("").classes("font-mono text-sm")

                # Results Table
                table_container = ui.column().classes("w-full mt-2")

                def show_status(message: str, is_success: bool):
                    status_banner.classes(remove="hidden bg-green-50 bg-red-50 border-green-500 border-red-500")
                    if is_success:
                        status_banner.classes(add="bg-green-50 border-l-4 border-green-500 text-green-900")
                    else:
                        status_banner.classes(add="bg-red-50 border-l-4 border-red-500 text-red-900")
                    status_text.text = message

                def run_query(target: str):
                    table_container.clear()
                    try:
                        db, sa = get_spanner_db(selected_persona.value)
                        query = f"SELECT id, first_name, last_name, ssn, email, phone_number FROM {target} LIMIT 10"
                        with db.snapshot() as snapshot:
                            raw_rows = list(snapshot.execute_sql(query))
                        
                        rows = [
                            {
                                "id": r[0][:8] + "...",
                                "first_name": r[1],
                                "last_name": r[2],
                                "ssn": r[3],
                                "email": r[4],
                                "phone_number": r[5],
                            }
                            for r in raw_rows
                        ]

                        show_status(f"SUCCESS: Retrieved {len(rows)} records from '{target}' using {selected_persona.value}.", True)

                        columns = [
                            {"name": "id", "label": "ID", "field": "id", "align": "left"},
                            {"name": "first_name", "label": "First Name", "field": "first_name", "align": "left"},
                            {"name": "last_name", "label": "Last Name", "field": "last_name", "align": "left"},
                            {"name": "ssn", "label": "SSN", "field": "ssn", "align": "center", "classes": "font-bold text-blue-700"},
                            {"name": "email", "label": "Email", "field": "email", "align": "left"},
                            {"name": "phone_number", "label": "Phone Number", "field": "phone_number", "align": "center", "classes": "font-bold text-teal-700"},
                        ]

                        with table_container:
                            ui.table(columns=columns, rows=rows, row_key="id").classes("w-full shadow rounded-lg border")

                    except PermissionDenied as pe:
                        show_status(f"SECURITY ENFORCEMENT (403 Permission Denied):\n{pe.message}", False)
                    except Exception as e:
                        show_status(f"ERROR: {str(e)}", False)

                def run_insert():
                    table_container.clear()
                    try:
                        db, sa = get_spanner_db(selected_persona.value)
                        test_id = str(uuid.uuid4())
                        sql = (
                            f"INSERT INTO customers (id, first_name, last_name, ssn, email, phone_number) "
                            f"VALUES ('{test_id}', 'Test', 'Auditor', '999-99-9999', 'audit@spanner.demo', '555-019-9999')"
                        )
                        def execute_tx(tx):
                            tx.execute_update(sql)

                        db.run_in_transaction(execute_tx)
                        show_status(f"SUCCESS: Record inserted successfully into 'customers' table by {selected_persona.value}!", True)
                    except PermissionDenied as pe:
                        show_status(f"SECURITY ENFORCEMENT (403 Permission Denied):\n{pe.message}", False)
                    except Exception as e:
                        show_status(f"ERROR: {str(e)}", False)

                btn_table.on_click(lambda: run_query("customers"))
                btn_view.on_click(lambda: run_query("customers_masked"))
                btn_insert.on_click(run_insert)

            # -----------------------------------------------------------------------------------------
            # TAB 2: DATABASE DDL & SCHEMA
            # -----------------------------------------------------------------------------------------
            with ui.tab_panel(tab_ddl).classes("p-0 gap-6 flex flex-col"):

                # Explanatory Overview Card
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    with ui.row().classes("items-center justify-between w-full"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("schema", size="1.5rem").classes("text-blue-600")
                            ui.label("Cloud Spanner FGAC Schema Architecture").classes("text-lg font-bold text-slate-800")
                        refresh_btn = ui.button("Refresh Live DDL", icon="refresh").props("flat color=primary")

                    ui.markdown("""
This Spanner database implements **Fine-Grained Access Control (FGAC)** using a combination of **Definer's Rights Views** (`SQL SECURITY DEFINER`) and **Database Roles**:
- **Strict Name Resolution**: All column references in views are qualified (`customers.id`, `customers.ssn`) as required by Cloud Spanner.
- **SQL SECURITY DEFINER**: Allows the `masked` role to query the masked view **without** needing access to the underlying `customers` table.
- **Dynamic Masking**: Uses `SUBSTR(column, -4)` to dynamically mask SSN (`XXX-XX-1234`) and phone numbers (`XXX-XXX-1234`).
                    """).classes("text-sm text-slate-600")

                # Section 1: Base Table DDL
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("1. Base Table", color="indigo").classes("text-xs font-bold")
                        ui.label("customers (Unmasked Raw Data)").classes("font-semibold text-slate-800")
                    ui.label("Contains the primary data including unmasked SSN and phone numbers.").classes("text-xs text-slate-500 mb-2")
                    ui.code(STATIC_DDL["table"], language="sql").classes("w-full text-xs")

                # Section 2: Definer's Rights View DDL
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("2. Definer's Rights View", color="teal").classes("text-xs font-bold")
                        ui.label("customers_masked (SQL SECURITY DEFINER)").classes("font-semibold text-slate-800")
                    ui.label("Executes with view definer privileges so users without base table access can read masked columns.").classes("text-xs text-slate-500 mb-2")
                    ui.code(STATIC_DDL["view"], language="sql").classes("w-full text-xs")

                # Section 3: Roles & Privileges DDL
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("3. Database Roles & Grants", color="purple").classes("text-xs font-bold")
                        ui.label("FGAC Privilege Definitions").classes("font-semibold text-slate-800")
                    ui.label("Defines readwrite, fullview, and masked database roles and assigns their object permissions.").classes("text-xs text-slate-500 mb-2")
                    ui.code(STATIC_DDL["roles"], language="sql").classes("w-full text-xs")

                # Section 4: Live Spanner DDL Output
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("terminal", size="1.2rem").classes("text-slate-600")
                        ui.label("Live Cloud Spanner DDL (Deployed)").classes("font-semibold text-slate-800")
                    ui.label(f"Retrieved live from Spanner instance '{DEFAULT_INSTANCE}' / database '{DEFAULT_DATABASE}':").classes("text-xs text-slate-500 mb-2")
                    
                    live_code_view = ui.code(fetch_live_ddl(), language="sql").classes("w-full text-xs")

                    def update_live_ddl():
                        live_code_view.content = fetch_live_ddl()
                        ui.notify("Refreshed live DDL from Cloud Spanner", color="positive")

                    refresh_btn.on_click(update_live_ddl)

            # -----------------------------------------------------------------------------------------
            # TAB 3: PYTHON CONNECTION & ROLE USAGE EXPLANATION
            # -----------------------------------------------------------------------------------------
            with ui.tab_panel(tab_conn).classes("p-0 gap-6 flex flex-col"):

                # Architecture Explanation Card
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("psychology", size="1.5rem").classes("text-indigo-600")
                        ui.label("Two-Tier FGAC Security: IAM Authentication + Database Authorization").classes("text-lg font-bold text-slate-800")

                    ui.markdown("""
* **Two-Tier Enforcement**: **Cloud IAM** authenticates the Service Account and validates which role it may assume via IAM Condition (`resource.name.endsWith('/databaseRoles/<role>')`). **Database Roles** authorize SQL table and view access.
* **Session Metadata**: The Python SDK embeds `database_role` into gRPC `CreateSession` requests to set the security context.
* **Why it's required**: FGAC service accounts have no blanket root access. You **must** specify the authorized database role.
                    """).classes("text-sm text-slate-700")

                    with ui.row().classes("w-full gap-4 mt-1"):
                        with ui.card().classes("flex-1 p-3 bg-slate-50 border text-xs"):
                            ui.label("1. Correct Role").classes("font-bold text-green-700")
                            ui.label("database_role='masked'").classes("font-mono text-slate-800")
                            ui.label("IAM condition passes -> Role privileges applied.").classes("text-slate-500 mt-1")
                        with ui.card().classes("flex-1 p-3 bg-slate-50 border text-xs"):
                            ui.label("2. Omitted Role").classes("font-bold text-red-700")
                            ui.label("database_role=None").classes("font-mono text-slate-800")
                            ui.label("Evaluates at DB root -> 403 sessions.create denied.").classes("text-slate-500 mt-1")
                        with ui.card().classes("flex-1 p-3 bg-slate-50 border text-xs"):
                            ui.label("3. Unauthorized Role").classes("font-bold text-amber-700")
                            ui.label("database_role='readwrite'").classes("font-mono text-slate-800")
                            ui.label("Violates IAM condition -> 403 databaseRoles.use denied.").classes("text-slate-500 mt-1")

                # Code Sample Card
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge("Python SDK", color="blue").classes("text-xs font-bold")
                        ui.label("Python Connection Pattern (via Service Account Impersonation)").classes("font-semibold text-slate-800")

                    ui.code("""import google.auth
from google.auth import impersonated_credentials
from google.cloud import spanner

# 1. Base caller credentials (e.g., from gcloud auth application-default login)
source_credentials, _ = google.auth.default()

# 2. Impersonate the target FGAC service account (No local keys needed!)
impersonated_creds = impersonated_credentials.Credentials(
    source_credentials=source_credentials,
    target_principal="spanner-fgac-masked@mague-tf.iam.gserviceaccount.com",
    target_scopes=["https://www.googleapis.com/auth/spanner.data"],
    lifetime=3600,
)

# 3. Create client with impersonated credentials
client = spanner.Client(project="mague-tf", credentials=impersonated_creds, disable_builtin_metrics=True)

# 4. Pass database_role to set gRPC session security context (REQUIRED for FGAC)
database = client.instance("shared-demos").database("fgac-demo", database_role="masked")

# 5. Queries execute under the 'masked' role's privileges
with database.snapshot() as snapshot:
    rows = list(snapshot.execute_sql("SELECT * FROM customers_masked LIMIT 5"))""", language="python").classes("w-full text-xs")

                # Interactive Live Playground Card
                with ui.card().classes("w-full shadow-md bg-white border border-slate-200"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("play_circle", size="1.3rem").classes("text-teal-600")
                        ui.label("Live Interactive Test: Compare Connection Behaviors").classes("font-semibold text-slate-800")
                    ui.label("Test Spanner behavior under three connection configurations using impersonated credentials:").classes("text-xs text-slate-500 mb-2")

                    with ui.row().classes("gap-3 flex-wrap"):
                        btn_test_valid = ui.button("1. Connect WITH database_role='masked' (Valid)", icon="check_circle").props("unelevated color=positive")
                        btn_test_norole = ui.button("2. Connect WITHOUT database_role (Omitted)", icon="cancel").props("unelevated color=negative")
                        btn_test_wrongrole = ui.button("3. Connect WITH database_role='readwrite' (Unauthorized)", icon="block").props("unelevated color=warning")

                    # Live output card
                    test_output_card = ui.card().classes("w-full p-4 mt-3 bg-slate-50 border border-slate-200 shadow-none")
                    test_output_label = ui.label("Click any button above to execute a real-time connection test against Cloud Spanner.").classes("font-mono text-xs text-slate-600")

                    def run_connection_test(scenario: str):
                        test_output_label.text = "Executing test against Cloud Spanner API..."
                        target_sa = f"spanner-fgac-masked@{DEFAULT_PROJECT}.iam.gserviceaccount.com"

                        try:
                            # Use Impersonated Credentials
                            source_creds, _ = google.auth.default()
                            impersonated_creds = impersonated_credentials.Credentials(
                                source_credentials=source_creds,
                                target_principal=target_sa,
                                target_scopes=["https://www.googleapis.com/auth/spanner.data"],
                                lifetime=3600,
                            )
                            c = spanner.Client(project=DEFAULT_PROJECT, credentials=impersonated_creds, disable_builtin_metrics=True)
                            inst = c.instance(DEFAULT_INSTANCE)

                            if scenario == "valid":
                                db = inst.database(DEFAULT_DATABASE, database_role="masked")
                                with db.snapshot() as s:
                                    row = list(s.execute_sql("SELECT id, first_name, last_name, ssn, phone_number FROM customers_masked LIMIT 1"))[0]
                                test_output_card.classes(remove="border-red-400 border-amber-400 bg-red-50 bg-amber-50", add="border-green-400 bg-green-50")
                                test_output_label.text = (
                                    f"✓ SUCCESS (200 OK): Session created with database_role='masked'.\n"
                                    f"IAM condition matched & SQL view privileges applied.\n"
                                    f"Sample Data: {row[1]} {row[2]} | SSN: {row[3]} | Phone: {row[4]}"
                                )

                            elif scenario == "norole":
                                db = inst.database(DEFAULT_DATABASE)
                                with db.snapshot() as s:
                                    list(s.execute_sql("SELECT * FROM customers_masked LIMIT 1"))
                                test_output_label.text = "Unexpected success!"

                            elif scenario == "wrongrole":
                                db = inst.database(DEFAULT_DATABASE, database_role="readwrite")
                                with db.snapshot() as s:
                                    list(s.execute_sql("SELECT * FROM customers LIMIT 1"))
                                test_output_label.text = "Unexpected success!"

                        except PermissionDenied as pe:
                            if scenario == "norole":
                                test_output_card.classes(remove="border-green-400 border-amber-400 bg-green-50 bg-amber-50", add="border-red-400 bg-red-50")
                                test_output_label.text = (
                                    "✗ EXPECTED FAILURE (403 Permission Denied — spanner.sessions.create):\n"
                                    "No blanket root access. FGAC service accounts must explicitly declare their assigned database_role."
                                )
                            elif scenario == "wrongrole":
                                test_output_card.classes(remove="border-green-400 border-red-400 bg-green-50 bg-red-50", add="border-amber-400 bg-amber-50")
                                test_output_label.text = (
                                    "✗ EXPECTED FAILURE (403 Permission Denied — spanner.databaseRoles.use):\n"
                                    "Unauthorized role. The service account's IAM condition only permits 'databaseRoles/masked', blocking 'readwrite'."
                                )
                        except Exception as ex:
                            test_output_label.text = f"Error: {type(ex).__name__}: {str(ex)}"

                    btn_test_valid.on_click(lambda: run_connection_test("valid"))
                    btn_test_norole.on_click(lambda: run_connection_test("norole"))
                    btn_test_wrongrole.on_click(lambda: run_connection_test("wrongrole"))

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Spanner FGAC Demo", port=8080, reload=False)
