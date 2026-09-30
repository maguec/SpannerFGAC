output "project_id" {
  description = "The Google Cloud Project ID"
  value       = var.project_id
}

output "instance_name" {
  description = "The effective Spanner Instance name"
  value       = local.effective_instance_name
}

output "database_name" {
  description = "The created Spanner Database name"
  value       = google_spanner_database.database.name
}

output "service_account_emails" {
  description = "Map of personas to their Google Cloud Service Account emails"
  value = {
    for k, sa in google_service_account.personas : k => sa.email
  }
}

output "database_roles" {
  description = "Map of personas to their Spanner Database Roles"
  value = {
    for k, p in local.fgac_roles : k => p.db_role
  }
}

output "impersonator_member" {
  description = "The IAM member identity granted serviceAccountTokenCreator to impersonate the personas"
  value       = local.impersonator_member
}
