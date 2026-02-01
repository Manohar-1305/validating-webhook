from flask import Flask, request, jsonify

app = Flask(__name__)

REQUIRED_LABELS = ["team", "environment"]

def is_privileged(pod_spec):
    containers = pod_spec.get("containers", [])
    for c in containers:
        sec = c.get("securityContext", {})
        if sec.get("privileged", False) is True:
            return True
    return False

@app.route("/validate", methods=["POST"])
def validate():
    review = request.get_json()
    req = review["request"]

    uid = req["uid"]
    obj = req["object"]

    metadata = obj.get("metadata", {})
    spec = obj.get("spec", {})

    # 1️⃣ Label validation
    labels = metadata.get("labels", {})
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

    # 2️⃣ Privileged container validation
    if is_privileged(spec):
        return jsonify({
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {
                "uid": uid,
                "allowed": False,
                "status": {
                    "message": "Privileged containers are not allowed"
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
