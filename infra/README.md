# Infra — Step 0 target system

This is the deliberately-simple system the diagnostic agent will monitor.
It is NOT the agent itself — see the project root `CLAUDE.md` for the full
picture. This folder's only job is to give you something real that can
break on demand, so later steps (Grafana alerting, the agent, MCP tools)
have a genuine target instead of an imagined one.

## What's here

```
infra/
├── terraform/        # Minimal EKS cluster (1 node group, 2 small nodes)
├── app/               # The backend service itself (Flask) + Dockerfile
└── k8s/                # Deployment/Service manifest to run it on EKS
```

## Setup order

### 1. Stand up the cluster

```bash
cd infra/terraform
terraform init
terraform apply
```

This takes 10-15 minutes (EKS control plane provisioning is slow — that's
normal, not a hang). Once done:

```bash
aws eks update-kubeconfig --region us-east-1 --name diagnostic-agent-demo
kubectl get nodes   # should show 2 nodes, Ready
```

### 2. Build and push the backend image

You'll need an ECR repo (or use Docker Hub if you'd rather skip ECR setup
for now — either works for a demo project).

```bash
cd infra/app

# Example using ECR — adjust account ID/region to yours
aws ecr create-repository --repository-name demo-backend
docker build -t demo-backend:latest .

aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.us-east-1.amazonaws.com

docker tag demo-backend:latest <your-account-id>.dkr.ecr.us-east-1.amazonaws.com/demo-backend:latest
docker push <your-account-id>.dkr.ecr.us-east-1.amazonaws.com/demo-backend:latest
```

Then update the `image:` line in `k8s/demo-backend.yaml` to point at your
pushed image.

### 3. Deploy it

```bash
kubectl apply -f infra/k8s/demo-backend.yaml
kubectl get pods -l app=demo-backend   # should show 2 pods, Running
```

### 4. Confirm it actually works

```bash
kubectl port-forward svc/demo-backend 8080:80
```

In another terminal:
```bash
curl localhost:8080/            # {"status": "ok", ...}
curl localhost:8080/metrics     # Prometheus-format output
```

### 5. Test the break switches — do this before wiring up Grafana

This is the step people skip and regret. Confirm the service can actually
fail on demand before you build alerting on top of it.

```bash
# Turn on forced 5xx errors
curl -X POST localhost:8080/break/5xx/on
curl localhost:8080/            # should now return 500

# Turn it back off
curl -X POST localhost:8080/break/5xx/off
curl localhost:8080/            # back to 200

# Crash one pod (simulates a real crash, triggers a restart)
curl -X POST localhost:8080/break/crash
kubectl get pods -l app=demo-backend   # watch restart count increase
```

If all of that behaves as expected, you have a real, breakable target.
**This is the point to stop and install Prometheus + connect Grafana** —
not before, since there'd be nothing real to scrape yet, and not much
later, since everything after this depends on alerting actually working
against this real service.

## What's deliberately NOT here yet

- No Prometheus/Grafana install — connect your already-existing Grafana
  setup to scrape this cluster once the service above is confirmed
  working. If Grafana needs Prometheus installed on this cluster first,
  `kube-prometheus-stack` via Helm is the standard path, but that's a
  separate step from this folder.
2. No frontend service — the SOPs already reference "homepage," so a
  frontend is a natural next addition once the backend + alerting loop is
  proven, not before.
3. No autoscaling, no multi-AZ HA, no ingress/TLS — none of that is needed
  to prove the diagnostic loop works, and adding it now would just be
  extra infrastructure to debug before the actual project (the agent)
  even starts.

## Cleaning up

EKS clusters cost money by the hour even when idle. When you're not
actively working on this:

```bash
cd infra/terraform
terraform destroy
```

You'll need to re-run steps 1-3 above next time, but that's a fair
trade for not paying for an idle cluster between work sessions.
