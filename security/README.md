# FlightDelay Trivy DevSecOps Gate

The Jenkins pipeline runs three blocking Trivy gates.

## 1. Source gate

It scans:

- dependency vulnerabilities from lock files;
- exposed secrets;
- Docker, Compose, Helm and Kubernetes misconfigurations;
- forbidden licenses;
- repository software components through CycloneDX and SPDX SBOMs.

## 2. Rendered manifest gate

It scans `flight-delay-rendered.yaml` after `helm template`, so security checks use the final Helm values rather than only the templates.

## 3. Image gate

It scans the locally built frontend and backend images for:

- vulnerabilities;
- embedded secrets;
- image and Dockerfile misconfigurations;
- forbidden licenses;
- CycloneDX and SPDX SBOM generation.

## Default policy

- Blocking severities: `HIGH,CRITICAL`
- Unfixed vulnerabilities: reported but excluded from the blocking vulnerability gate
- License gate: `CRITICAL` only
- Trivy image: pinned by `TRIVY_IMAGE`
- Reports: `security-reports/`

The Jenkins build archives JSON, SARIF, table reports and SBOMs even when a gate fails.

## Run locally

```bash
chmod +x scripts/security/trivy-gate.sh
scripts/security/trivy-gate.sh source

helm template flight-delay-dev \
  deploy/helm/flight-delay \
  --namespace flight-delay-helm \
  --values deploy/helm/flight-delay/values-dev.yaml \
  > flight-delay-rendered.yaml

scripts/security/trivy-gate.sh config flight-delay-rendered.yaml

scripts/security/trivy-gate.sh images \
  mehdibenzaied/flight-delay-frontend:test \
  mehdibenzaied/flight-delay-backend:test
```

## Handling findings

Fix the vulnerable dependency, leaked secret or insecure configuration first.

Use `.trivyignore` only for a reviewed exception. Do not add broad patterns or suppress an entire class of findings.
