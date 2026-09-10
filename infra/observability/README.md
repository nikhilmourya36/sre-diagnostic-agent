# Observability — Prometheus + Grafana on EKS

This installs `kube-prometheus-stack` (Prometheus + Grafana + Alertmanager)
onto the EKS cluster from `infra/terraform/`, and wires up scraping + one
real alert for the demo backend service.

Do this AFTER `infra/app` is deployed and you've confirmed the service
responds and its break switches work (see `infra/README.md` step 5). No
point installing monitoring before there's anything real to monitor.

## 1. Install kube-prometheus-stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f infra/observability/values.yaml \
  --set grafana.adminPassword="<pick-a-real-password-here>"
```

This takes a few minutes. Confirm everything came up:

```bash
kubectl get pods -n monitoring
```

You should see pods for prometheus, grafana, alertmanager, node-exporter
(one per node), and kube-state-metrics, all `Running`.

## 2. Wire up scraping for the demo backend

```bash
kubectl apply -f infra/k8s/demo-backend.yaml       # picks up the named "http" port fix
kubectl apply -f infra/observability/service-monitor.yaml
```

Confirm Prometheus actually sees it — port-forward into Prometheus's UI:

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```

Open `http://localhost:9090/targets` — look for `demo-backend` in the
target list with state `UP`. **If it's not there or it's `DOWN`, stop here
and fix it before continuing** — nothing downstream (alerts, Grafana
dashboards, the agent) works if Prometheus isn't actually scraping the
service.

## 3. Add the alert rule

```bash
kubectl apply -f infra/observability/alert-rule.yaml
```

Confirm it loaded — in the Prometheus UI, check `http://localhost:9090/alerts`.
You should see `DemoBackendHighErrorRate` listed with state `Inactive`
(meaning: loaded and being evaluated, just not currently firing).

## 4. Access Grafana

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
```

Open `http://localhost:3000` — log in as `admin` with the password you
set in step 1. Prometheus is already wired as Grafana's datasource by the
chart, so you don't need to configure that manually.

You won't have a custom dashboard for `demo_backend_error_rate` yet — the
chart ships with generic Kubernetes/node dashboards, not one for your
app's custom metric. Building that dashboard is a good next step, but not
required to prove alerting works — Prometheus's own `/alerts` page is
enough for that.

## 5. Prove the whole loop fires, end to end

This is the real test — don't skip it.

```bash
# In one terminal, keep a port-forward open to the backend
kubectl port-forward svc/demo-backend 8080:80

# In another terminal, trigger the failure
curl -X POST localhost:8080/break/5xx/on

# Generate some traffic so the error rate metric actually has data —
# a single request isn't enough for a meaningful rate
for i in $(seq 1 20); do curl -s localhost:8080/ > /dev/null; done
```

Wait ~1-2 minutes (the rule requires the threshold to hold for 1 minute),
then check `http://localhost:9090/alerts` again — `DemoBackendHighErrorRate`
should now show `Firing` (it may sit in `Pending` briefly first, which is
expected).

Then turn it back off and confirm it resolves:

```bash
curl -X POST localhost:8080/break/5xx/off
```

Give it another minute or two and confirm the alert goes back to
`Inactive`.

**If this works, you have a real, end-to-end alerting pipeline** — a real
service, a real metric, a real Prometheus rule, actually firing and
resolving based on real traffic. Everything after this (Alertmanager →
webhook → agent) builds on top of something proven, not assumed.

## What's next after this

Alertmanager needs a **receiver** configured to actually send this alert
somewhere (Slack directly, and eventually the agent's webhook). That's the
next piece — worth doing as its own step once this is confirmed working,
not bundled in here.

## Cleaning up

```bash
helm uninstall kube-prometheus-stack -n monitoring
kubectl delete namespace monitoring
```

Do this before `terraform destroy`-ing the whole cluster, or just let the
cluster teardown handle it — either is fine for a demo environment.
