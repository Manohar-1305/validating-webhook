# Validating Webhooks: Preventing Misconfigured Workloads with Kubernetes

This repository demonstrates a production-grade Kubernetes Validating Admission Webhook implemented using Python Flask, secured with TLS (SAN-based certificates), and deployed directly into a Kubernetes cluster.

The webhook enforces mandatory labels at admission time, preventing misconfigured workloads from ever entering the cluster.

Real-world problem this solves

In real Kubernetes environments:

Pods are created by humans, CI pipelines, and automation
- Labels like team and environment are often optional or forgotten
- Cost allocation, ownership tracking, and security enforcement break silently
Once a bad resource is created, remediation is already late.

* This webhook enforces standards at the API server boundary, where enforcement is guaranteed.

# What this webhook does
Intercepts Pod CREATE requests

# Validates the presence of required labels:
team
environment
Rejects the request if labels are missing

# What it intentionally does NOT do

- No mutation
- No Kubernetes API calls
- No RBAC requirements
- No external dependencies

# This is pure validation with zero side effects.

* Project structure
```
validating-webhook/
├── app.py
├── Dockerfile
├── requirements.txt
├── san.cnf
├── manifests/
│   ├── namespace.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── validating-webhook.yaml
```
Webhook implementation (Flask)

app.py
```
from flask import Flask, request, jsonify

app = Flask(__name__)

REQUIRED_LABELS = ["team", "environment"]

@app.route("/validate", methods=["POST"])
def validate():
    review = request.get_json()
    req = review["request"]

    uid = req["uid"]
    obj = req["object"]

    labels = obj.get("metadata", {}).get("labels", {})
    missing = [l for l in REQUIRED_LABELS if l not in labels]

    if missing:
        return jsonify({
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {
                "uid": uid,
                "allowed": False,
                "status": {
                    "message": f"Missing required labels: {missing}"
                }
            }
        })

    return jsonify({
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "response": {
            "uid": uid,
            "allowed": True
        }
    })

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8443,
        ssl_context=("/certs/tls.crt", "/certs/tls.key")
    )
```
* Python dependencies

# requirements.txt
```
flask==3.0.0
```


* Minimal dependencies keep the admission path fast and reliable.

# Docker image
```
Dockerfile

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8443

CMD ["python", "app.py"]
```

# Build the image:
```
docker build -t manoharshetty507/validating-webhook:v1 .
```
# TLS with SAN (mandatory)

* Kubernetes requires Subject Alternative Names in webhook certificates.

san.cnf
```
[ req ]
default_bits       = 2048
prompt             = no
default_md         = sha256
distinguished_name = dn
req_extensions     = req_ext

[ dn ]
CN = validating-webhook.webhook.svc

[ req_ext ]
subjectAltName = @alt_names

[ alt_names ]
DNS.1 = validating-webhook
DNS.2 = validating-webhook.webhook
DNS.3 = validating-webhook.webhook.svc
DNS.4 = validating-webhook.webhook.svc.cluster.local
```

# Generate certificates:
```
openssl genrsa -out tls.key 2048

openssl req -x509 -new \
  -key tls.key \
  -out tls.crt \
  -days 365 \
  -config san.cnf \
  -extensions req_ext
```
# Import image into containerd (no registry required)
```
ctr -n k8s.io images import <(docker save manoharshetty507/validating-webhook:v1)
```

# Verify:
```
ctr -n k8s.io images ls | grep validating-webhook
```
Kubernetes deployment steps
1. Create namespace

manifests/namespace.yaml
```
apiVersion: v1
kind: Namespace
metadata:
  name: webhook
```

* Apply:
```
kubectl apply -f manifests/namespace.yaml
```
# 2. TLS Secret using the certificates ✅ (explicitly included)

* Create the TLS secret that will be mounted into the webhook pods:
```
kubectl create secret tls validating-webhook-tls \
  --cert=tls.crt \
  --key=tls.key \
  -n webhook
```

This secret provides the HTTPS identity required by the Kubernetes API server.

# 3. Deployment and Service

The webhook runs with:

2 replicas (HA for admission path)
TLS mounted read-only
Internal ClusterIP service
* Apply all manifests:
```
kubectl apply -f manifests/
```

Check pod status:
```
kubectl get pods -n webhook
```

Check logs:
```
kubectl logs -f <webhook-pod-name> -n webhook
```
* ValidatingWebhookConfiguration (v1)

# Encode CA bundle:
```
base64 -w0 tls.crt
```

manifests/validating-webhook.yaml
```
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: validate-required-labels
webhooks:
- name: labels.webhook.example.com
  admissionReviewVersions: ["v1"]
  sideEffects: None
  failurePolicy: Fail
  rules:
  - apiGroups: [""]
    apiVersions: ["v1"]
    operations: ["CREATE"]
    resources: ["pods"]
  clientConfig:
    service:
      name: validating-webhook
      namespace: webhook
      path: /validate
      port: 443
    caBundle: <PASTE_BASE64_CA_BUNDLE_HERE>
```
*Verification
#Rejected Pod
```
apiVersion: v1
kind: Pod
metadata:
  name: bad-pod
spec:
  containers:
  - name: nginx
    image: nginx
```

Result:
```
Error from server: Missing required labels: ['team', 'environment']
```
* Accepted Pod
```
apiVersion: v1
kind: Pod
metadata:
  name: good-pod
  labels:
    team: platform
    environment: prod
spec:
  containers:
  - name: nginx
    image: nginx
```

Pod schedules normally.
Production rules (do not ignore)
Keep the webhook stateless
Never call external services
Keep response time minimal
Use replicas ≥ 2
failurePolicy: Fail for enforcement
Remember: validating webhooks block the API server

Final note
This pattern is used by:
platform engineering teams
security enforcement layers
compliance and governance systems

It prevents bad workloads before they exist, which is the only time enforcement truly works.

Once you adopt admission control correctly, Kubernetes stops being just an orchestrator and starts becoming a policy-enforced platform.
