provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  create_instance = var.create_instance || var.instance_name == "" || var.instance_name == null
  instance_name   = local.create_instance ? (var.instance_name != "" && var.instance_name != null ? var.instance_name : "spanner-fgac-demo") : var.instance_name

  fgac_roles = {
    "readwrite" = {
      display_name = "ReadWrite User"
      db_role      = "readwrite"
    }
    "fullview" = {
      display_name = "FullView User"
      db_role      = "fullview"
    }
    "masked" = {
      display_name = "Masked User"
      db_role      = "masked"
    }
  }
}

# ---------------------------------------------------------------------------------------------------------------------
# Cloud Spanner Instance
# Creates a 100 PU Standard instance with no backups if instance_name is empty or create_instance is true.
# Otherwise, looks up the existing instance (defaults to "shared-demos").
# ---------------------------------------------------------------------------------------------------------------------
resource "google_spanner_instance" "this" {
  count                        = local.create_instance ? 1 : 0
  name                         = local.instance_name
  config                       = var.spanner_config
  display_name                 = "Spanner FGAC Demo Instance"
  edition                      = "STANDARD"
  processing_units             = 100
  default_backup_schedule_type = "NONE"
}

data "google_spanner_instance" "existing" {
  count = local.create_instance ? 0 : 1
  name  = var.instance_name
}

locals {
  effective_instance_name = local.create_instance ? google_spanner_instance.this[0].name : data.google_spanner_instance.existing[0].name
}

# ---------------------------------------------------------------------------------------------------------------------
# Cloud Spanner Database & FGAC DDL
# ---------------------------------------------------------------------------------------------------------------------
resource "google_spanner_database" "database" {
  instance            = local.effective_instance_name
  name                = var.database_id
  deletion_protection = var.deletion_protection

  ddl = [
    # 1. Base table storing full unmasked data
    <<-EOT
    CREATE TABLE customers (
      id STRING(36) NOT NULL,
      first_name STRING(64) NOT NULL,
      last_name STRING(64) NOT NULL,
      ssn STRING(11) NOT NULL,
      email STRING(128) NOT NULL,
      phone_number STRING(32) NOT NULL,
    ) PRIMARY KEY (id)
    EOT
    ,
    # 2. Definer's rights view providing masked SSN and Phone Number (qualified for strict name resolution mode)
    <<-EOT
    CREATE VIEW customers_masked SQL SECURITY DEFINER AS
    SELECT
      customers.id,
      customers.first_name,
      customers.last_name,
      CONCAT('XXX-XX-', SUBSTR(customers.ssn, -4)) AS ssn,
      customers.email,
      CONCAT('XXX-XXX-', SUBSTR(customers.phone_number, -4)) AS phone_number
    FROM customers
    EOT
    ,
    # 3. Database roles for Fine-Grained Access Control
    "CREATE ROLE readwrite",
    "CREATE ROLE fullview",
    "CREATE ROLE masked",

    # 4. Privilege grants to database roles
    # ReadWrite: full SELECT, INSERT, UPDATE, DELETE on base table and view
    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE customers TO ROLE readwrite",
    "GRANT SELECT ON VIEW customers_masked TO ROLE readwrite",

    # FullView: SELECT on base table (unmasked) and view (read-only)
    "GRANT SELECT ON TABLE customers TO ROLE fullview",
    "GRANT SELECT ON VIEW customers_masked TO ROLE fullview",

    # Masked: SELECT only on masked view (NO access to base customers table)
    "GRANT SELECT ON VIEW customers_masked TO ROLE masked"
  ]
}

# ---------------------------------------------------------------------------------------------------------------------
# IAM Service Accounts & Local Key Generation
# ---------------------------------------------------------------------------------------------------------------------
resource "google_service_account" "personas" {
  for_each     = local.fgac_roles
  account_id   = "spanner-fgac-${each.key}"
  display_name = "Spanner FGAC ${each.value.display_name}"
}

# ---------------------------------------------------------------------------------------------------------------------
# Service Account Impersonation (No local key downloads)
# Grants caller permission to generate short-lived tokens via google.auth.impersonated_credentials
# ---------------------------------------------------------------------------------------------------------------------
data "google_client_openid_userinfo" "me" {}

locals {
  impersonator_member = var.impersonator_member != "" ? (
    startswith(var.impersonator_member, "user:") ||
    startswith(var.impersonator_member, "serviceAccount:") ||
    startswith(var.impersonator_member, "group:")
    ? var.impersonator_member
    : "user:${var.impersonator_member}"
  ) : "user:${data.google_client_openid_userinfo.me.email}"
}

resource "google_service_account_iam_member" "token_creator" {
  for_each           = google_service_account.personas
  service_account_id = each.value.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = local.impersonator_member
}

# ---------------------------------------------------------------------------------------------------------------------
# Database IAM Bindings
# ---------------------------------------------------------------------------------------------------------------------

# 1. FGAC Personas: Assigned roles/spanner.fineGrainedAccessUser to enable FGAC
resource "google_spanner_database_iam_member" "fgac_access_user" {
  for_each = local.fgac_roles
  instance = local.effective_instance_name
  database = google_spanner_database.database.name
  role     = "roles/spanner.fineGrainedAccessUser"
  member   = "serviceAccount:${google_service_account.personas[each.key].email}"
}

# 3. FGAC Personas: Assigned roles/spanner.databaseRoleUser with IAM condition restricting to specific DB role
resource "google_spanner_database_iam_member" "fgac_role_user" {
  for_each = local.fgac_roles
  instance = local.effective_instance_name
  database = google_spanner_database.database.name
  role     = "roles/spanner.databaseRoleUser"
  member   = "serviceAccount:${google_service_account.personas[each.key].email}"

  condition {
    title       = "DatabaseRole_${each.key}"
    description = "Grants access exclusively to database role ${each.value.db_role}"
    expression  = "resource.type == 'spanner.googleapis.com/DatabaseRole' && resource.name.endsWith('/databaseRoles/${each.value.db_role}')"
  }
}
