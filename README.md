# NetworkMongoTest: Multi-Environment Policy GitOps & Automated Verification
### Automated Testing & GitOps Repository for NetTrace AI (MongoDB Hackathon)

> **Main Application Engine:** [`BhavyaBhimani/NetworkMongo`](https://github.com/BhavyaBhimani/NetworkMongo) — Core multi-agent reasoning, Gemini AI integration, Web Dashboard UI, and MongoDB models.

This repository serves as the **declarative Infrastructure-as-Code (GitOps) repository** for network policies managed across enterprise environments (`eng`, `dev`, `qa`, `pat`, `prod`).

---

## 1. Environment Directory Structure

```
environments/
  ├── eng/   ───► Engineering (Auto-merge permitted for safe rules)
  ├── dev/   ───► Development (Auto-merge permitted for safe rules)
  ├── qa/    ───► Quality Assurance & Staging (Canary testing & auto-rollback)
  ├── pat/   ───► Pre-Acceptance Testing (Protected: Requires Network Lead Gate)
  └── prod/  ───► Production (Protected: Requires Manager Sign-Off)
```

Each environment contains a declarative `network-policy.json` specifying active firewall rules, ingress/egress permissions, port ranges, protocols, and CIDR blocks.

---

## 2. GitHub Actions Automation Workflow

### Workflow 1: PR Validation & Pre-Action Gate (`.github/workflows/pr-validate.yml`)
- Triggered whenever a PR modifies any file in `environments/**`.
- The **PR Validator Agent** checks:
  1. Collection-level MongoDB schema compliance (`$jsonSchema`).
  2. Historical incident memory (recalling past outages on target ports).
  3. Active emergency drifts (detecting midnight un-attested hotfixes).
  4. Environment protection matrices:
     - Non-prod (`eng`, `dev`): **Auto-Merges** PR if all guardrails pass.
     - Protected (`pat`, `prod`): Halts in `AWAITING_APPROVAL` until Manager sign-off.
     - Prohibited (e.g. port 22 on `0.0.0.0/0`): **Rejects** PR with detailed explanation.

### Workflow 2: Post-Merge Canary Probe & Fallback Rollback (`.github/workflows/deploy-and-verify.yml`)
- Triggered when changes are merged to `main`.
- Step 1: Deploys policy revision to target environment & records atomic snapshot in MongoDB.
- Step 2: Runs synthetic network test probes (connectivity, zero-trust isolation, latency).
- **On Success**: Generates SLSA/in-toto Cryptographic Attestation signed with HMAC-SHA256 and committed to the MongoDB hash chain ledger.
- **On Failure (Fallback Part)**:
  - Immediately restores previous known-good state in MongoDB.
  - Automatically creates and commits an **Autonomous Git Revert** (`[AUTO-REVERT] ...`).
  - Logs failure episode into MongoDB Agentic Memory.

### Workflow 3: End-to-End Test Matrix (`.github/workflows/automated-test-matrix.yml`)
- Runs all 5 scenarios end-to-end on pushes, PRs, or via 1-click **Run workflow** button.

---

## 3. Running the Automated Test Suite Locally

You can run the full multi-environment test suite locally with one command:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the end-to-end Git PR automation suite
python scripts/simulate_git_pr_suite.py
```

### Scenarios Covered in the Suite:
- **Test Case 1:** PR targeting `dev` -> Validates -> Auto-merges -> Deploys -> Canary passes -> SLSA Attestation signed.
- **Test Case 2:** PR targeting `prod` -> Enforces Pre-Action Human Manager approval gate.
- **Test Case 3 (Fallback):** PR targeting `qa` with flawed rule -> Canary fails -> Autonomous rollback in MongoDB -> Autonomous Git Revert committed!
- **Test Case 4:** Prohibited public SSH rule -> Blocked before merge.
- **Test Case 5:** Midnight manual drift -> Reconciles into MongoDB memory -> Subsequent PR halts on conflict (Zero Cold Start!).
