"""
Service Account Impersonation helper for Cloud Spanner FGAC demo.
Eliminates the need for downloading local service account key JSON files.
"""

import json
import os
import google.auth
from google.auth import impersonated_credentials
from google.cloud import spanner

os.environ["SPANNER_DISABLE_BUILTIN_METRICS"] = "true"

def get_target_sa_email(role: str, project_id: str) -> str:
    """Returns the standard service account email for a given FGAC persona role."""
    return f"spanner-fgac-{role}@{project_id}.iam.gserviceaccount.com"

def get_impersonated_client(
    target_sa_email: str,
    project_id: str | None = None,
    default_project: str = "mague-tf",
) -> spanner.Client:
    """
    Instantiates a Cloud Spanner Client using short-lived impersonated credentials.
    """
    source_credentials, detected_project = google.auth.default()
    effective_project = project_id or default_project or detected_project

    impersonated_creds = impersonated_credentials.Credentials(
        source_credentials=source_credentials,
        target_principal=target_sa_email,
        target_scopes=["https://www.googleapis.com/auth/spanner.data"],
        lifetime=3600,
    )

    return spanner.Client(
        project=effective_project,
        credentials=impersonated_creds,
        disable_builtin_metrics=True,
    )
