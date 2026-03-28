# Template: Docker → Artifact Registry → Cloud Run → GitHub + Cloud Build

Use this document as a checklist for a **containerized web app** on **Google Cloud Platform** with **continuous deployment from GitHub**. Replace every placeholder in the table before you start.

## Placeholders (fill these in)

| Placeholder | Description | Your value |
|-------------|-------------|------------|
| `PROJECT_ID` | GCP project ID | |
| `REGION` | GCP region (e.g. `europe-west3`, `us-central1`) | |
| `AR_REPO` | Artifact Registry repository name (Docker format) | |
| `IMAGE_NAME` | Image name inside that repository | |
| `SERVICE_NAME` | Cloud Run service name | |
| `GITHUB_OWNER` / `GITHUB_REPO` | GitHub repository (`owner/repo`) | |
| `BUILD_SA` | Service account email used by the Cloud Build trigger (optional; default is project Cloud Build SA) | |
| `MAIN_BRANCH` | Branch that deploys to production (usually `main`) | |

**Artifact Registry hostname:** `{REGION}-docker.pkg.dev/{PROJECT_ID}/{AR_REPO}/{IMAGE_NAME}:TAG`

---

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`) installed and authenticated
- [Docker](https://docs.docker.com/get-docker/) installed (for local build and manual push)
- A GCP project with billing enabled (if required by your org)
- GitHub repository containing at minimum: `Dockerfile`, application source, and `cloudbuild.yaml` at the paths you configure

---

## Phase 1 — Local development with Docker

### 1.1 Dockerfile expectations

- Container must listen on the port given by the **`PORT`** environment variable (Cloud Run sets this at runtime). For local tests you can use `8080`.
- Expose the same port in the image if helpful; Cloud Run sends traffic to `PORT`.

### 1.2 Build and run locally

```bash
cd /path/to/your/app
docker build -t myapp:local .
docker run --rm -p 8080:8080 -e PORT=8080 myapp:local
```

Open `http://localhost:8080` and confirm the app works.

### 1.3 Apple Silicon (Mac) — important for Cloud Run

Cloud Run runs **`linux/amd64`**. If you build on Apple Silicon without a platform flag, the image may be **`arm64`** only and Cloud Run will reject it.

**Option A — build flag (good for one-off pushes):**

```bash
docker build --platform linux/amd64 -t myapp:local .
```

**Option B — Dockerfile (keeps default platform explicit):**

```dockerfile
FROM --platform=linux/amd64 YOUR_BASE_IMAGE
```

**Option C — Cloud Build:** ensure `cloudbuild.yaml` includes `docker build --platform linux/amd64` (builds on GCP are often amd64 already; the flag keeps behavior explicit).

---

## Phase 2 — Artifact Registry and Cloud Run (manual path)

### 2.1 Enable APIs

```bash
gcloud config set project PROJECT_ID
gcloud services enable artifactregistry.googleapis.com run.googleapis.com
```

### 2.2 Create a Docker Artifact Registry repository

```bash
gcloud artifacts repositories create AR_REPO \
  --repository-format=docker \
  --location=REGION \
  --description="Docker images for SERVICE_NAME"
```

If it already exists, skip this step.

### 2.3 Configure Docker authentication

```bash
gcloud auth configure-docker REGION-docker.pkg.dev
```

### 2.4 Build, tag, push

```bash
export TAG=v1
docker build --platform linux/amd64 \
  -t REGION-docker.pkg.dev/PROJECT_ID/AR_REPO/IMAGE_NAME:${TAG} .
docker push REGION-docker.pkg.dev/PROJECT_ID/AR_REPO/IMAGE_NAME:${TAG}
```

### 2.5 Deploy to Cloud Run (public URL example)

```bash
gcloud run deploy SERVICE_NAME \
  --image REGION-docker.pkg.dev/PROJECT_ID/AR_REPO/IMAGE_NAME:${TAG} \
  --region REGION \
  --platform managed \
  --allow-unauthenticated \
  --port 8080
```

Note the **Service URL** in the output and verify it in a browser.

### 2.6 Application Default Credentials quota project (optional)

If `gcloud` warns that the quota project does not match:

```bash
gcloud auth application-default set-quota-project PROJECT_ID
```

---

## Phase 3 — CI/CD: GitHub + Cloud Build + Cloud Run

### 3.1 Repository layout

At minimum (adjust paths if your trigger uses subdirectories):

- `Dockerfile`
- `cloudbuild.yaml` (repository root is typical)
- Application source and dependency files (e.g. `requirements.txt`)

### 3.2 Example `cloudbuild.yaml` pattern

Your file should:

1. `docker build` (prefer `--platform linux/amd64`) with image tag including **`SHORT_SHA`** for GitHub-triggered builds.
2. `docker push` (both `SHORT_SHA` and `latest` is a common pattern).
3. `gcloud run deploy` with the same image reference, **`--region`**, **`--platform managed`**, and public access if required (`--allow-unauthenticated`).

Use **substitutions** for region, Artifact Registry repo name, service name, and image name so one YAML works across environments:

- `_REGION`
- `_AR_REPO`
- `_SERVICE_NAME`
- `_IMAGE_NAME`

GitHub-connected triggers usually provide **`SHORT_SHA`** automatically.

### 3.3 Connect GitHub in Google Cloud

1. Enable **Cloud Build API**: `gcloud services enable cloudbuild.googleapis.com`
2. In **Cloud Build → Connect repository**, connect **GitHub** and select `GITHUB_OWNER/GITHUB_REPO`.
3. **Create trigger**:
   - Event: Push to branch matching `^MAIN_BRANCH$` (e.g. `^main$`).
   - Configuration: **Cloud Build configuration file** → path `cloudbuild.yaml` (or your path).
   - Region: match your Cloud Run / org requirements (e.g. `REGION`).
   - Service account: default Cloud Build SA or a **user-managed** SA (see below).

Avoid relying solely on **Autodetected** config if you need a specific `cloudbuild.yaml` with deploy steps.

### 3.4 IAM for the build (executing) service account

The identity that runs the build steps must be able to **push** to Artifact Registry and **deploy** Cloud Run.

Typical roles on **project** `PROJECT_ID` (tighten to resources when your org allows):

| Role | Purpose |
|------|---------|
| `roles/artifactregistry.writer` | Push container images |
| `roles/run.admin` | Deploy and update Cloud Run services |
| `roles/iam.serviceAccountUser` | Act as the Cloud Run runtime service account during deploy |
| `roles/logging.logWriter` | Write build logs to Cloud Logging |

If builds fail on **Cloud Storage** access, add `roles/storage.objectAdmin` or (broader) `roles/storage.admin` per your security policy.

**User-managed trigger SA:** grant the roles above to **`BUILD_SA`**. Also allow Cloud Build to use that SA:

```bash
PROJECT_NUMBER=$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding BUILD_SA \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

**Conditional IAM bindings:** If `gcloud` asks for a condition when adding roles, choose **no condition** (`--condition=None`) unless you intentionally want time- or tag-based access. Expired conditions silently remove access.

### 3.5 Verify the pipeline

1. Push a small change to `MAIN_BRANCH`.
2. **Cloud Build → History**: confirm success for build, push, and deploy steps.
3. **Cloud Run → Revisions**: confirm a new revision and traffic routing.
4. Open the service URL and confirm the change.

---

## Troubleshooting (quick reference)

| Symptom | Likely cause | What to check |
|--------|----------------|---------------|
| Cloud Run: manifest must support **amd64/linux** | Image built for `arm64` (common on Mac) | Rebuild with `--platform linux/amd64`; fix `cloudbuild.yaml` |
| Push denied to Artifact Registry | Missing `artifactregistry.writer` or wrong project | IAM on `BUILD_SA` or user running `docker push` |
| `gcloud run deploy` permission denied | Missing `run.admin` or `iam.serviceAccountUser` | IAM on executing SA |
| Build never starts | Trigger branch regex or disabled trigger | Trigger settings; GitHub app access to repo |
| Build fails on `SHORT_SHA` empty | Manual run without substitutions | Use GitHub trigger or pass `SHORT_SHA` in manual submit |
| Long YAML after `gcloud projects add-iam-policy-binding` | Normal | Success line: `Updated IAM policy for project [...]` |

---

## Reuse checklist for a new use case

1. Copy **Dockerfile** pattern and ensure **`PORT`** is honored.
2. Set **`cloudbuild.yaml`** substitutions to the new `REGION`, `AR_REPO`, `IMAGE_NAME`, `SERVICE_NAME`.
3. Create (or reuse) Artifact Registry repo in **`REGION`**.
4. Create Cloud Run service **`SERVICE_NAME`** (first deploy can be manual or via first pipeline run).
5. Create or clone a **trigger** pointing at the new GitHub repo / branch / YAML path.
6. Confirm **IAM** on the executing service account for that project.
7. Document your filled **placeholder table** for the team (without secrets).

---

## Security notes

- Do not commit **service account keys**; prefer Workload Identity / default Cloud Build + IAM.
- Prefer least-privilege IAM (repository-level or service-level bindings) once the pipeline is stable.
- Rotate and audit triggers and connected GitHub repositories periodically.
