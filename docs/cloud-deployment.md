# TEEVR AI — Cloud Deployment

## Target
Google Cloud Run, region asia-south1 (Telangana demo). If a Gemini capability is unavailable in asia-south1, use a disclosed supported region with explicit consent.

## Provision
```bash
cd teevra-ai/infrastructure/terraform
terraform init
terraform apply -var project_id=$GCP_PROJECT_ID -var region=$GCP_REGION
```

## Deploy services (Cloud Run)
```bash
gcloud run deploy teevra-api-gateway --source services/api-gateway --region asia-south1 --allow-unauthenticated
gcloud run deploy teevra-recovery-agent --source services/recovery-agent --region asia-south1 --no-allow-unauthenticated
gcloud run deploy teevra-heat-guardian --source services/heat-guardian-agent --region asia-south1 --no-allow-unauthenticated
```

## IAM (least privilege)
- Cloud Run service identity: pubsub.subscriber, eventarc.eventReceiver, datastore.user (Firestore), secretmanager.secretAccessor (Secret Manager), bigquery.dataEditor (optional analytics)
- No service-account keys in repo; use Application Default Credentials locally, workload identity in Cloud Run.

## Secrets
Google Cloud Secret Manager for Firebase config, Vertex AI endpoints. Local mode uses .env and simulated providers.

## Expected resources & cost
Cloud Run (3 services, low traffic), Firestore (datastore mode), Pub/Sub, Eventarc, Secret Manager, BigQuery (small demo dataset). Vertex AI only if Gemini used (optional; local fallback is free).

## Environment variables
See .env.example. VERTEX_AI_LOCATION and GEMINI_TEXT_MODEL are configurable; local mode uses a deterministic Gemini fallback.
