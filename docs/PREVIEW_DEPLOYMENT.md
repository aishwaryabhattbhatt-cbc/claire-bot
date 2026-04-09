# Preview Deployment Setup

This document describes the CI/CD setup for automatic preview and production deployments using GitHub Actions and Google Cloud Run.

## Overview

The deployment workflow handles three scenarios:

1. **Main Branch Pushes** → Production deployment to `clairebot` service
2. **Feature Branch Pushes/PRs** → Preview deployment to `clairebot-preview-{branch-name}` service
3. **Branch Deletions** → Automatic cleanup of preview services

## Deployment Workflow

### Preview Deployments (Non-Main Branches)

When you push to any branch other than `main` or open a PR:

1. Docker image is built and pushed to GCR
2. Service is deployed to `clairebot-preview-{sanitized-branch-name}`
3. Preview URL is automatically posted as a PR comment
4. Service is accessible immediately for testing

### Production Deployments (Main Branch)

When commits are pushed to `main`:

1. Docker image is built and pushed to GCR
2. Production service (`clairebot`) is updated with new image
3. No PR comment is created

### Cleanup

When a branch is deleted:

1. The corresponding preview service is automatically deleted
2. No manual cleanup needed

## Configuration Requirements

### GitHub Secrets

The following secrets must be configured in your GitHub repository settings:

```
GCP_PROJECT_ID
GCP_WORKLOAD_IDENTITY_PROVIDER
GCP_SERVICE_ACCOUNT
```

**Setup steps:**

1. Go to **Settings → Secrets and variables → Actions**
2. Add each secret with the values from your GCP project

### Service Account Permissions

The GCP service account must have these roles:

- `Cloud Run Admin` - Deploy and manage Cloud Run services
- `Service Account User` - Use the runtime service account
- `Artifact Registry Writer` - Push Docker images to GCR
- `Secret Manager Secret Accessor` - Access secrets (GOOGLE_API_KEY)

### GCP Workload Identity Setup

Configure workload identity federation:

```bash
# Set variables
export PROJECT_ID=your-project-id
export GITHUB_REPO=your-github-org/claire-bot

# Create identity pool
gcloud iam workload-identity-pools create github \
  --project=$PROJECT_ID \
  --location=global \
  --display-name="GitHub"

# Create provider
gcloud iam workload-identity-pools providers create-oidc github \
  --project=$PROJECT_ID \
  --location=global \
  --workload-identity-pool=github \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub" \
  --issuer-uri=https://token.actions.githubusercontent.com

# Get the provider resource name
gcloud iam workload-identity-pools describe github \
  --project=$PROJECT_ID \
  --location=global \
  --format='value(name)'

# Create service account
gcloud iam service-accounts create github-actions \
  --project=$PROJECT_ID \
  --display-name="GitHub Actions"

# Grant permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/run.admin

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/artifactregistry.writer

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountUser

# Allow GitHub to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding \
  github-actions@$PROJECT_ID.iam.gserviceaccount.com \
  --project=$PROJECT_ID \
  --role=roles/iam.workloadIdentityUser \
  --member=principalSet://iam.googleapis.com/projects/$PROJECT_ID/locations/global/workloadIdentityPools/github/attribute.repository/$GITHUB_REPO
```

## Environment Variables

Both preview and production services are deployed with the same environment configuration:

```yaml
APP_ENV: production (main) or preview (branches)
LOG_LEVEL: INFO
LLM_PROVIDER: gemini
GEMINI_MODEL: gemini-2.5-flash
ENABLE_SHEETS_WRITER: false
UPLOAD_DIR: /tmp/uploads
PROCESSED_DIR: /tmp/processed
GOOGLE_API_KEY: (from Secret Manager)
```

To modify these, edit `.github/workflows/deploy.yml` in the `gcloud run deploy` commands.

## Preview Service Features

- **Auto-generated URLs:** Each preview has a unique Cloud Run URL
- **Same config:** Uses identical environment setup as production
- **Auto-cleanup:** Deleted when branch is closed/merged
- **PR comments:** Preview URL automatically posted on PR creation
- **Concurrent deployments:** Multiple preview services can run simultaneously

## Testing a Preview Deployment

1. Create a feature branch and push changes:
   ```bash
   git checkout -b feature/my-feature
   git push origin feature/my-feature
   ```

2. Open a PR on GitHub
3. Wait for deployment to complete (typically 2-5 minutes)
4. Look for the preview URL comment on the PR
5. Click the link to test your changes
6. Once approved, merge the PR
7. Preview service is automatically deleted

## Monitoring Deployments

### Check deployment status:

```bash
# List all preview services
gcloud run services list --region=us-central1 --filter="name:clairebot-preview"

# View specific preview service
gcloud run services describe clairebot-preview-my-branch --region=us-central1

# View production service
gcloud run services describe clairebot --region=us-central1

# Check recent deployments
gcloud run services list --region=us-central1 | grep clairebot
```

### View logs:

```bash
# Preview service logs
gcloud run logs read clairebot-preview-my-branch --region=us-central1

# Production service logs
gcloud run logs read clairebot --region=us-central1
```

## Troubleshooting

### Preview service not deployed

1. Check workflow logs in GitHub Actions
2. Verify GCP credentials are configured correctly
3. Ensure service account has necessary permissions
4. Check GCR can be accessed: `gcloud auth configure-docker`

### PR comment not posted

1. Workflow likely failed at deploy step - check logs
2. Verify `GITHUB_TOKEN` is available (should be automatic)
3. Check PR number is correctly passed

### Service not accessible

1. Verify service was created: `gcloud run services list --region=us-central1`
2. Check Cloud Run service is set to "Allow unauthenticated invocations"
3. Verify environment variables are correct

### Cleanup didn't work

1. Check workflow logs for delete step
2. Manually delete if needed:
   ```bash
   gcloud run services delete clairebot-preview-branch-name --region=us-central1
   ```

## Cost Optimization

Preview services use the following settings to minimize costs:

- `min-instances=0` - Scales to zero when not in use
- `max-instances=2` - Prevents runaway costs
- `memory=1Gi` - Same as production
- `cpu=1` - Same as production
- Auto-deleted when branch is closed

Estimated cost per preview service per month (idle): ~$0-2 USD

## Advanced Configuration

### Changing deployment regions

Edit `.github/workflows/deploy.yml` and change:
```yaml
REGION: us-central1  # Change this
```

### Modifying environment variables

Update the `--set-env-vars` flags in both deploy jobs:
```bash
--set-env-vars=KEY1=value1,KEY2=value2,...
```

### Custom domain for preview services

```bash
# After deployment, map a custom domain
gcloud run services update clairebot-preview-my-branch \
  --region=us-central1 \
  --set-domain=preview-my-feature.example.com
```

## Next Steps

1. Configure GitHub secrets in your repository
2. Set up GCP workload identity (follow setup steps above)
3. Push a test branch to verify workflow runs
4. Check the PR for preview URL comment
5. Test the preview service
