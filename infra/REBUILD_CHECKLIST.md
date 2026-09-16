# Rebuild Checklist — after `terraform destroy`

Use this after tearing everything down (e.g. overnight cost savings).
Every config file referenced here is already correct and tested — this is
just re-running known-good commands in order, not debugging from scratch.

Run all commands from `infra/terraform` unless a `cd` is shown.
Estimated time: ~20-25 min, mostly EKS's own provisioning wait.

---

## 1. Recreate the cluster + ECR repo

```powershell
cd infra\terraform
terraform apply
```

Type `yes` when prompted. Takes 10-15 min — this is the slow part, not a
hang.

Grab the ECR URL from the output once done:
```powershell
terraform output ecr_repository_url
```

## 2. Point kubectl at the new cluster

New cluster = new endpoint, even with the same name:
```powershell
aws eks update-kubeconfig --region us-east-1 --name diagnostic-agent-demo
kubectl get nodes
```
Confirm both nodes show `Ready` before continuing.

## 3. Push the demo backend image to the fresh ECR repo

The image itself is still on your local Docker (unaffected by destroy) —
just re-tag and push it to the new repo:

```powershell
aws ecr get-login-password --region us-east-1 | Out-String -Stream | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

docker tag demo-backend:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/demo-backend:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/demo-backend:latest
```

(Use `terraform output ecr_repository_url` from step 1 to get the exact
URI instead of guessing the account ID.)

## 4. Update and apply the K8s manifest

`infra/k8s/demo-backend.yaml`'s `image:` line needs to point at the
**new** ECR repo (the URI is the same shape but the repo was just
recreated — double check it matches step 1's output).

```powershell
kubectl apply -f infra\k8s\demo-backend.yaml
kubectl get pods -l app=demo-backend
```
Confirm 2 pods `Running` before continuing.

## 5. Reinstall Prometheus + Grafana + Alertmanager (all in one shot this time)

Unlike the first time through, apply BOTH values files together from the
start — the PagerDuty wiring is already proven correct, no need to
re-debug it:

```powershell
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

cd ..\observability
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack `
  --namespace monitoring --create-namespace `
  -f values.yaml `
  -f alertmanager-values.local.yaml `
  --set grafana.adminPassword="<pick-a-real-password>"
```

`alertmanager-values.local.yaml` already has your real PagerDuty routing
key in it from before (it's a local file, survived the destroy) — no need
to recreate or re-edit it, unless you've lost it, in which case: copy
`alertmanager-values.yaml` again and re-paste the key.

## 6. Wire up scraping and the alert rule

```powershell
kubectl apply -f service-monitor.yaml
kubectl apply -f alert-rule.yaml
```

## 7. Confirm the operator sync succeeded (no PagerDuty config errors)

```powershell
kubectl logs -n monitoring -l app.kubernetes.io/name=kube-prometheus-stack-prometheus-operator --tail=20
```
Should show clean `sync alertmanager` / `sync prometheus` lines, no
`undefined receiver` or other errors.

## 8. Confirm Prometheus sees the target

```powershell
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```
Open `http://localhost:9090/targets` — `demo-backend` should show `UP`.

## 9. Full end-to-end trigger test

```powershell
kubectl port-forward svc/demo-backend 8080:80
```
In another terminal:
```powershell
curl.exe -X POST http://localhost:8080/break/5xx/on
curl.exe -X POST http://localhost:8080/break/5xx/on   # run twice — per-pod state, see known limitation below
for ($i=1; $i -le 20; $i++) { curl.exe -s http://localhost:8080/ | Out-Null }
```

Wait ~2 min, then check:
- `http://localhost:9090/alerts` — `DemoBackendHighErrorRate` firing?
- PagerDuty — real incident created?
- Slack `#sre-alerts` — incident posted there?

**Known limitation reminder:** if the alert won't clear after you flip
the switch off, it's the per-pod in-memory state issue (documented in
`infra/README.md`) — force a clean state with:
```powershell
kubectl rollout restart deployment demo-backend
```

---

## When you're done for the session again

```powershell
cd infra\terraform
terraform destroy
```

Confirms with `yes`. Repeat this checklist next time.

## What you do NOT need to redo, ever (survives destroy)

- This checklist itself, and all other repo files
- `alertmanager-values.local.yaml` (your real PagerDuty key)
- The local Docker image (`demo-backend:latest`) — only needs re-pushing,
  not rebuilding, unless you've changed `app.py`
- PagerDuty service/integration setup
- Slack app, bot tokens, `#sre-alerts` channel
- Confluence SOP pages and sync script progress
