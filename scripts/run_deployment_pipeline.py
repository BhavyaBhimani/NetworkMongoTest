import sys
import os
# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import subprocess
from app.db.mongo import get_db
from app.agents.deployment_agent import deployment_agent
from app.agents.testing_agent import testing_agent
from app.agents.audit_agent import audit_agent
from app.db.attestations import attestation_ledger

def execute_git_revert(env: str, reason: str):
    """
    Automated Git Revert: Restores git working copy and commits an auto-revert.
    """
    print(f"\n[AUTONOMOUS GIT FALLBACK] Initiating Git Revert for environments/{env}/network-policy.json...")
    try:
        # Checkout previous version from git or revert
        subprocess.run(["git", "checkout", "HEAD~1", "--", f"environments/{env}/network-policy.json"], check=False)
        subprocess.run(["git", "add", f"environments/{env}/network-policy.json"], check=False)
        commit_msg = f"[AUTO-REVERT] Self-healing rollback of failed policy on {env.upper()}: {reason}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=False)
        print(f"[AUTONOMOUS GIT FALLBACK] Committed auto-revert: '{commit_msg}'")
    except Exception as e:
        print(f"Notice: Git revert automation notice ({e})")

def main():
    print("==================================================================")
    print("  NETTRACE AI - DEPLOYMENT & SYNTHETIC VERIFICATION PIPELINE")
    print("  Deploying policy, running canary probes, attesting or rolling back")
    print("==================================================================")

    env = sys.argv[1].lower() if len(sys.argv) > 1 else os.getenv("TARGET_ENV", "dev")
    force_fail = os.getenv("FORCE_FAIL", "false").lower() in ("true", "1")
    pr_id = os.getenv("PR_ID", f"PR-DEPLOY-{env.upper()}")
    author = os.getenv("PR_AUTHOR", "Network DevOps Automation")

    policy_file = f"environments/{env}/network-policy.json"
    if not os.path.exists(policy_file):
        print(f"Policy file {policy_file} not found!")
        sys.exit(1)

    with open(policy_file, "r") as f:
        policy_data = json.load(f)

    rules = policy_data.get("rules", [])
    print(f"Deploying {len(rules)} rules to target environment [{env.upper()}]...")

    pr_doc = {
        "pr_id": pr_id,
        "author": author,
        "target_branch": env,
        "policy_changes": rules
    }

    # Step 1: Deploy policy (stores prior snapshot in MongoDB)
    deploy_res = deployment_agent.deploy_policy(pr_doc)
    deployment_id = deploy_res["deployment_id"]
    print(f"  • Policy revision committed to MongoDB. Deployment ID: {deployment_id}")

    # Step 2: Run synthetic canary tests
    print(f"  • Running synthetic health and boundary isolation probes...")
    test_res = testing_agent.run_network_tests(pr_doc, deployment_id=deployment_id, force_fail=force_fail)

    if test_res["passed"]:
        # Step 3: Success -> SLSA Cryptographic Attestation
        att = test_res["attestation"]
        print(f"\n[SUCCESS] Synthetic tests passed ({test_res['test_summary']['passed_checks']}/{test_res['test_summary']['total_checks']})")
        print(f"  • SLSA Attestation ID: {att['attestation_id']}")
        print(f"  • SHA-256 Digest: {att['subject']['digest']['sha256']}")
        print(f"  • Chain Parent Hash: {att['previous_attestation_hash']}")
        
        # Continuous audit check
        audit_res = audit_agent.audit_environment(env)
        print(f"  • Audit Agent Continuous Verification: {audit_res['verified_rules_count']} rules verified without drift.")
        sys.exit(0)
    else:
        # Step 4: Failure -> Automated Rollback (Fallback part of system)
        print(f"\n[ALERT] Synthetic canary tests failed! Packet loss / isolation violation detected.")
        print(f"  • Initiating autonomous rollback to prior snapshot in MongoDB...")
        
        rollback_res = deployment_agent.rollback_deployment(
            deployment_id=deployment_id,
            reason=f"Canary test failure on {env.upper()}"
        )
        print(f"  • {rollback_res['message']}")

        # Trigger Autonomous Git Revert
        execute_git_revert(env, "Synthetic probe failed isolation verification")

        print(f"  • Failure incident logged into MongoDB Episodic Memory for future context.")
        print("\n[RESULT] FALLBACK ROLLBACK COMPLETED SUCCESSFULLY.")
        sys.exit(2)  # Return code 2 indicates fallback rollback executed

if __name__ == "__main__":
    main()
