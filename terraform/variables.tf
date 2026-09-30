variable "project_id" {
  description = "The Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region for resources"
  type        = string
  default     = "us-central1"
}

variable "instance_name" {
  description = "Name of the Spanner instance. Default is 'shared-demos'. If set to an empty string (\"\") or null, a new Spanner instance will be provisioned with 100 PU, standard edition, and no backups."
  type        = string
  default     = "shared-demos"
}

variable "create_instance" {
  description = "Set to true to explicitly create the Spanner instance even if instance_name is specified. Automatically true if instance_name is empty or null."
  type        = bool
  default     = false
}

variable "spanner_config" {
  description = "Instance configuration for Spanner if creating a new instance"
  type        = string
  default     = "regional-us-central1"
}

variable "database_id" {
  description = "The ID of the Spanner database to create"
  type        = string
  default     = "fgac-demo"
}

variable "impersonator_member" {
  description = "IAM member identity allowed to impersonate the FGAC service accounts (e.g., 'user:you@example.com' or 'group:team@example.com'). If empty, defaults to current authenticated gcloud user."
  type        = string
  default     = ""
}

variable "deletion_protection" {
  description = "Whether to enable deletion protection on the database"
  type        = bool
  default     = false
}
