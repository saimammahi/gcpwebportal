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
| `BUILD_SA` | User-managed service account email for the trigger (optional; if unset, trigger uses legacy Cloud Build SA) | |
| `EXEC_SA` | **Executor** for IAM grants: either `{PROJECT_NUMBER}@cloudbuild.gserviceaccount.com` or `BUILD_SA` — see §3.7 | |
| `MAIN_BRANCH` | Branch that deploys to production (usually `main`) | |

**Artifact Registry hostname:** `{REGION}-docker.pkg.dev/{PROJECT_ID}/{AR_REPO}/{IMAGE_NAME}:TAG`

---

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`) installed and authenticated
- [Docker](https://docs.docker.com/get-docker/) installed (for local build and manual push)
- A GCP project with billing enabled (if required by your org)
- GitHub repository containing at minimum: `Dockerfile`, application source, and `cloudbuild.yaml` at the paths you configure

**Cloud Build setup order (Phase 3):** enable APIs (§3.3) → understand identities (§3.4) → connect GitHub (§3.5) → create trigger (§3.6) → grant **`EXEC_SA`** (§3.7) → optional **`BUILD_SA`** impersonation (§3.8) → verify (§3.10).

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

### 3.3 Enable Cloud Build (create / turn on the product)

Cloud Build is a **managed build service**: it runs your `cloudbuild.yaml` on Google infrastructure when a trigger fires (for example on `git push`). You do not provision a VM yourself—you **enable APIs**, **connect the Git repository**, and **create triggers**.

**Required APIs** (enable once per project):

```bash
gcloud config set project PROJECT_ID

gcloud services enable \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  logging.googleapis.com
```

| API | Typical need |
|-----|----------------|
| `cloudbuild.googleapis.com` | Run builds and triggers |
| `artifactregistry.googleapis.com` | Push images from the pipeline (same project as registry) |
| `run.googleapis.com` | Deploy/update Cloud Run in this project |
| `cloudresourcemanager.googleapis.com`, `iam.googleapis.com` | IAM and resource operations during setup |
| `logging.googleapis.com` | Build logs in Cloud Logging |

**Console:** open [Cloud Build](https://console.cloud.google.com/cloud-build) and enable the API if prompted.

**Billing:** attach a **billing account** to `PROJECT_ID` if required; builds consume build minutes.

**Who can enable APIs:** usually **`roles/owner`** or **`roles/serviceusage.serviceUsageAdmin`** on the project.

---

### 3.4 Identities and access (who needs what)

| Identity | Email / pattern | Role in the pipeline |
|----------|-----------------|----------------------|
| **You (human)** | `user:you@company.com` | Installs the GitHub App, creates triggers, edits IAM, runs `gcloud`. |
| **Legacy Cloud Build service account** | `{PROJECT_NUMBER}@cloudbuild.gserviceaccount.com` | Default **executor** when the trigger **Service account** is **None**. Runs steps in `cloudbuild.yaml`. Grant **Artifact Registry**, **Cloud Run**, and **logging** to this SA unless you use a custom executor SA. |
| **Cloud Build Service Agent** | `service-{PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com` | Google-managed; used internally. You rarely assign project roles to it for app deploys. See [Configure access for the Cloud Build SA](https://cloud.google.com/build/docs/securing-builds/configure-access-for-cloud-build-service-account). |
| **User-managed executor SA (optional)** | `BUILD_SA` | If the trigger **selects** this SA, **it** runs build steps. Grant the same deploy/push roles to **`BUILD_SA`**, not only to the legacy Cloud Build SA. |
| **Cloud Run runtime SA** | Often `{PROJECT_NUMBER}-compute@developer.gserviceaccount.com` | Identity **inside** the running container. The **deploying** principal needs **`iam.serviceAccountUser`** on this SA so `gcloud run deploy` can attach it. |

**Project number:**

```bash
gcloud projects describe PROJECT_ID --format='value(projectNumber)'
```

---

### 3.5 Connect GitHub to Cloud Build

1. Select project **`PROJECT_ID`** in the console.
2. **Cloud Build → Repositories** (or **Triggers → Connect repository**).
3. Choose **GitHub** (**Cloud Build GitHub App**).
4. Authenticate and **install** the app on the org/account; grant access to **`GITHUB_OWNER/GITHUB_REPO`** (prefer **selected repos** over “all”).
5. Complete the wizard; the repo should appear for trigger creation.

**Permissions:** GitHub side—ability to install the app on the repo. GCP side—roles that allow creating connections (often **Owner** / **Editor** or a custom role with `cloudbuild.connections.create`). Details: [Connect to a GitHub repository](https://cloud.google.com/build/docs/automating-builds/github/connect-repo-github).

If the UI offers **Developer Connect** / **2nd gen** repositories, use the path your organization standardizes; both can back triggers.

---

### 3.6 Create a Cloud Build trigger (field-by-field)

1. **Cloud Build → Triggers → Create trigger**.
2. **Name:** e.g. `deploy-SERVICE_NAME-MAIN_BRANCH`.
3. **Region:** trigger region (e.g. `REGION`); align with org policy.
4. **Event:** **Push to a branch**.
5. **Branch:** regex for production branch, e.g. `^main$` for `MAIN_BRANCH=main`.
6. **Source / Repository:** connected **`GITHUB_OWNER/GITHUB_REPO`**.
7. **Configuration type:** **Cloud Build configuration file (yaml or json)** — avoid **Autodetected** if you need a fixed pipeline (build + push + deploy).
8. **Cloud Build configuration file:** path in repo, usually `cloudbuild.yaml`.
9. **Substitution variables (optional):** `_REGION`, `_AR_REPO`, `_SERVICE_NAME`, `_IMAGE_NAME` if not hard-coded in YAML.
10. **Service account:** **None** → executor is `{PROJECT_NUMBER}@cloudbuild.gserviceaccount.com`. Or choose **`BUILD_SA`** (then apply §3.7 to **`BUILD_SA`** and §3.8 for impersonation).
11. **Save.** Use **Run** to test without a new commit.

GitHub triggers normally supply **`SHORT_SHA`** automatically for image tags.

---

### 3.7 Grant the executing service account access (required)

The **executor** (§3.4) must push to Artifact Registry and deploy Cloud Run. Set **`EXEC_SA`** to either:

- `{PROJECT_NUMBER}@cloudbuild.gserviceaccount.com` (default trigger), or  
- **`BUILD_SA`** if the trigger uses it.

```bash
PROJECT_ID=PROJECT_ID
EXEC_SA=REPLACE_WITH_EXECUTING_SERVICE_ACCOUNT_EMAIL

for ROLE in \
  roles/artifactregistry.writer \
  roles/run.admin \
  roles/iam.serviceAccountUser \
  roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${EXEC_SA}" \
    --role="$ROLE" \
    --condition=None
done
```

| Role | Why |
|------|-----|
| `roles/artifactregistry.writer` | `docker push` to Artifact Registry |
| `roles/run.admin` | `gcloud run deploy` |
| `roles/iam.serviceAccountUser` | Use the Cloud Run **runtime** service account on deploy |
| `roles/logging.logWriter` | Write logs to Cloud Logging |

**Storage errors during build:** add `roles/storage.objectAdmin` or `roles/storage.admin` on the project for **`EXEC_SA`** if required by your setup (`--condition=None`).

**Note:** `gcloud projects add-iam-policy-binding` may print the **entire IAM policy**; success is indicated by **`Updated IAM policy for project [PROJECT_ID]`**.

**Conditional IAM:** use **`--condition=None`** for long-lived CI access. Time-bound conditions that have **expired** remove access with no obvious error until the build fails.

---

### 3.8 User-managed executor SA (`BUILD_SA`) — impersonation

If the trigger runs as **`BUILD_SA`**, the legacy Cloud Build SA must be allowed to act as **`BUILD_SA`**:

```bash
PROJECT_NUMBER=$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')

gcloud iam service-accounts add-iam-policy-binding BUILD_SA \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

Apply **§3.7** to **`BUILD_SA`** (not only to `{PROJECT_NUMBER}@cloudbuild.gserviceaccount.com`).

---

### 3.9 Manual build (optional)

```bash
cd /path/to/repo
gcloud builds submit . --config=cloudbuild.yaml \
  --substitutions=SHORT_SHA=manual-$(date +%Y%m%d%H%M)
```

`SHORT_SHA` must be set if your YAML uses it in image tags.

---

### 3.10 Verify the pipeline

1. Push a small change to `MAIN_BRANCH`.
2. **Cloud Build → History**: build, push, and deploy steps succeed.
3. **Cloud Run → Revisions**: new revision receives traffic.
4. Open the service URL and confirm the change.

---

## Troubleshooting (quick reference)

| Symptom | Likely cause | What to check |
|--------|----------------|---------------|
| Cannot enable **Cloud Build API** / APIs stay disabled | Billing, org policy, or missing `serviceusage.serviceUsageAdmin` | Billing account on project; org admin; §3.3 |
| **Connect repository** fails or greyed out | Insufficient GCP IAM to create connections | Owner/Editor or role with Cloud Build connection permissions; §3.5 |
| **GitHub** install fails | Missing org admin approval or repo access | GitHub org settings; app install scope (repo list) |
| Cloud Run: manifest must support **amd64/linux** | Image built for `arm64` (common on Mac) | Rebuild with `--platform linux/amd64`; fix `cloudbuild.yaml` |
| Push denied to Artifact Registry | Missing `artifactregistry.writer` or wrong project | IAM on **`EXEC_SA`** (§3.7) or on user running `docker push` |
| `gcloud run deploy` permission denied | Missing `run.admin` or `iam.serviceAccountUser` | IAM on **`EXEC_SA`**; runtime SA user grant |
| Build never starts | Trigger branch regex, disabled trigger, or webhook | Trigger UI; GitHub app still has repo access; §3.6 |
| Build fails on `SHORT_SHA` empty | Manual run without substitutions | GitHub trigger or `--substitutions=SHORT_SHA=...`; §3.9 |
| User-managed SA: build fails immediately | Cloud Build cannot impersonate **`BUILD_SA`** | §3.8 binding on **`BUILD_SA`** |
| Long YAML after `gcloud projects add-iam-policy-binding` | Normal | Success line: `Updated IAM policy for project [...]` |

---

## Reuse checklist for a new use case

1. Fill the **placeholder table** (top of doc) for the new app.
2. Copy **Dockerfile** pattern; ensure **`PORT`** is honored; use **`linux/amd64`** for Cloud Run (§1.3).
3. Set **`cloudbuild.yaml`** substitutions: `REGION`, `AR_REPO`, `IMAGE_NAME`, `SERVICE_NAME`.
4. **Enable APIs** per §3.3; confirm **billing** on `PROJECT_ID`.
5. Create (or reuse) **Artifact Registry** in **`REGION`**; deploy **Cloud Run** once manually if you want a known-good baseline (Phase 2).
6. **Connect GitHub** (§3.5), then **create a trigger** (§3.6): branch regex, YAML path, executor SA.
7. Grant **§3.7** to **`EXEC_SA`**; if using **`BUILD_SA`**, add **§3.8** impersonation.
8. **Verify** with §3.10 (push → History → Revisions → URL).
9. Store the filled placeholder table for the team (**no secrets**, no JSON keys).

---

## Security notes

- Do not commit **service account keys**; prefer Workload Identity / default Cloud Build + IAM.
- Prefer least-privilege IAM (repository-level or service-level bindings) once the pipeline is stable.
- Rotate and audit triggers and connected GitHub repositories periodically.
