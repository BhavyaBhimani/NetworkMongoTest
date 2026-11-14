import sys
import os
# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import subprocess
from app.db.mongo import get_db
from app.agents.validator_agent import validator_agent
from app.agents.audit_agent import audit_agent

def get_git_diff_policies():
    """
    Finds which environment network-policy.json files were modified in the PR.
    """
    envs = ["eng", "qa", "dev", "pat", "prod"]
    changed_policies = []

    # Check git diff against base branch (e.g. main/HEAD~1)
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        changed_files = [line.strip() for line in diff_output.splitlines() if line.strip()]
    except Exception:
        # Fallback to scanning all environment files if not in git diff
        changed_files = [f"environments/{e}/network-policy.json" for e in envs]

    for env in envs:
        policy_path = f"environments/{env}/network-policy.json"
        if any(policy_path in f for f in changed_files) or not changed_files:
            if os.path.exists(policy_path):
                try:
                    with open(policy_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        changed_policies.append({"env": env, "data": data})
                except Exception as e:
                    print(f"Error reading {policy_path}: {e}")

    # Default to dev if none specifically found
    if not changed_policies and os.path.exists("environments/dev/network-policy.json"):
        with open("environments/dev/network-policy.json", "r") as f:
            changed_policies.append({"env": "dev", "data": json.load(f)})

    return changed_policies

def main():
    print("==================================================================")
    print("  NETTRACE AI - GITHUB PR VALIDATE WORKFLOW (PRE-ACTION GATE)")
    print("  Evaluating Network Policy Diffs against MongoDB Guardrails")
    print("==================================================================")

    pr_author = os.getenv("PR_AUTHOR", "Developer (User A)")
    pr_id = os.getenv("PR_ID", "PR-GH-ACTION")

    changed = get_git_diff_policies()
    if not changed:
        print("No environment policy modifications detected. Skipping validation.")
        sys.exit(0)

    overall_approved = True
    requires_human_approval = False

    for item in changed:
        env = item["env"]
        policy_data = item["data"]
        rules = policy_data.get("rules", [])

        print(f"\nEvaluating target environment: [{env.upper()}] with {len(rules)} rule(s)")

        pr_mock = {
            "pr_id": f"{pr_id}-{env}",
            "author": pr_author,
            "target_branch": env,
            "policy_changes": rules
        }

        val = validator_agent.validate_pr(pr_mock)
        print(f"  • Decision: {'APPROVED' if val['approved'] else 'REJECTED'}")
        print(f"  • Risk Score: {val['risk_level']}")
        print(f"  • Human Authority Sign-Off Required: {val['requires_human_approval']}")
        if val.get("llm_assisted"):
            print(f"  • Cognitive AI: Evaluated by {val.get('llm_model')}")
        
        for reason in val.get("reasons", []):
            print(f"    - {reason}")
        for note in val.get("context_notes", []):
            print(f"    [MongoDB Context] {note}")

        # Persist PR status in MongoDB so local/central Web UI updates in real-time
        try:
            from datetime import datetime
            db = get_db()
            db_status = "AWAITING_APPROVAL" if val["requires_human_approval"] else ("MERGED" if val["approved"] else "REJECTED")
            db.pull_requests.update_one(
                {"pr_id": pr_mock["pr_id"]},
                {
                    "$set": {
                        "pr_id": pr_mock["pr_id"],
                        "title": os.getenv("PR_TITLE", f"Policy Update: {env.upper()} infrastructure"),
                        "author": pr_author,
                        "target_branch": env,
                        "policy_changes": rules,
                        "status": db_status,
                        "validation_result": val,
                        "updated_at": datetime.utcnow()
                    },
                    "$setOnInsert": {
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
        except Exception as e:
            print(f"Notice: MongoDB status sync notice ({e})")

        if not val["approved"]:
            overall_approved = False
        if val["requires_human_approval"]:
            requires_human_approval = True

    # Output for GitHub Actions
    gh_output = os.getenv("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"approved={str(overall_approved).lower()}\n")
            f.write(f"requires_human={str(requires_human_approval).lower()}\n")

    if not overall_approved:
        print("\n[RESULT] PR REJECTED: Security or active drift guardrails violated.")
        sys.exit(1)
    elif requires_human_approval:
        print("\n[RESULT] PR AWAITING APPROVAL: Protected branch requires Network Team Lead sign-off.")
        sys.exit(0)
    else:
        print("\n[RESULT] PR APPROVED: All checks passed. Eligible for automated merge!")
        sys.exit(0)

if __name__ == "__main__":
    main()
