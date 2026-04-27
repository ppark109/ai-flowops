# Private VM Deployment

AI FlowOps can be deployed to the private demo VM with the manual GitHub Actions
workflow in `.github/workflows/deploy-vm.yml`.

The workflow is intentionally manual. A push to `main` runs CI, but does not
deploy by itself.

## What the Workflow Does

1. Checks out the repository.
2. Installs Python dependencies.
3. Runs `ruff check .`.
4. Runs `pytest`.
5. Builds the Docker image on the GitHub runner.
6. Connects the runner to the tailnet with `tailscale/github-action@v4`.
7. SSHes to the private VM.
8. Updates `/opt/ai-flowops` to the workflow commit.
9. Builds `ai-flowops:local` on the VM.
10. Replaces only the `ai-flowops-app` container.
11. Keeps the app bound privately at `127.0.0.1:18080:8000`.
12. Verifies `http://127.0.0.1:18080/healthz` on the VM.

## Required GitHub Secrets

Set these repository or environment secrets before running the workflow:

- `TS_OAUTH_CLIENT_ID`
- `TS_OAUTH_SECRET`
- `AI_FLOWOPS_VM_HOST`
- `AI_FLOWOPS_VM_USER`
- `AI_FLOWOPS_VM_SSH_KEY`

`AI_FLOWOPS_VM_HOST` should be the VM tailnet DNS name or Tailscale IP.
`AI_FLOWOPS_VM_USER` is usually `ubuntu`.
`AI_FLOWOPS_VM_SSH_KEY` is the private key used for the deployment SSH user.

No OpenAI API key, Codex credential, or local `.env` file is required or copied.

## VM Resource Boundaries

The workflow is scoped to the AI FlowOps deployment:

- app directory: `/opt/ai-flowops`
- Docker image: `ai-flowops:local`
- Docker container: `ai-flowops-app`
- Docker volume: `ai-flowops-data`
- private bind: `127.0.0.1:18080:8000`

It does not modify unrelated user services or shared VM projects.

## Manual Run

In GitHub:

1. Open **Actions**.
2. Select **deploy-vm**.
3. Click **Run workflow**.
4. Select `main`.
5. Start the run.

After it completes, view the private app through the existing SSH/Tailscale
access path at `http://127.0.0.1:18080`.
