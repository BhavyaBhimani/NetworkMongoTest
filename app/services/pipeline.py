import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from app.db.mongo import get_db
from app.agents.validator_agent import validator_agent
from app.agents.deployment_agent import deployment_agent
from app.agents.testing_agent import testing_agent
from app.agents.audit_agent import audit_agent

class PipelineOrchestrator:
    def __init__(self):
        self.db = get_db()

    def create_pull_request(
        self,
        title: str,
        author: str,
        target_branch: str,
        policy_changes: list,
        source_branch: str = "feature/network-update",
        auto_run: bool = True
    ) -> Dict[str, Any]:
        """
        Creates a new Pull Request and triggers the Validation Pipeline.
        """
        pr_id = f"PR-{uuid.uuid4().hex[:6].upper()}"
        pr_doc = {
            "pr_id": pr_id,
            "title": title,
            "author": author,
            "target_branch": target_branch.lower(),
            "source_branch": source_branch,
            "policy_changes": policy_changes,
            "status": "OPEN",
            "validation_result": None,
            "deployment_result": None,
            "test_result": None,
            "attestation_id": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        self.db.pull_requests.insert_one(pr_doc)

        if auto_run:
            return self.run_validation_pipeline(pr_id)

        clean = {k: v for k, v in pr_doc.items() if k != "_id"}
        return clean

    def run_validation_pipeline(self, pr_id: str) -> Dict[str, Any]:
        """
        Runs the PR Validate workflow (GitHub Action simulation).
        Enforces policy BEFORE any action can take place.
        """
        pr = self.db.pull_requests.find_one({"pr_id": pr_id})
        if not pr:
            return {"error": "PR not found"}

        self.db.pull_requests.update_one(
            {"pr_id": pr_id},
            {"$set": {"status": "VALIDATING", "updated_at": datetime.utcnow()}}
        )

        validation = validator_agent.validate_pr(pr)

        if not validation["approved"]:
            new_status = "REJECTED"
        elif validation["requires_human_approval"]:
            new_status = "AWAITING_APPROVAL"
        else:
            new_status = "MERGED"

        self.db.pull_requests.update_one(
            {"pr_id": pr_id},
            {
                "$set": {
                    "status": new_status,
                    "validation_result": validation,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        # If auto-merged (non-prod branch approved), trigger deployment pipeline automatically!
        if new_status == "MERGED":
            deploy_res = self.run_deployment_pipeline(pr_id)
            return {
                "pr_id": pr_id,
                "validation": validation,
                "deployment": deploy_res,
                "status": deploy_res.get("final_status", "MERGED")
            }

        return {
            "pr_id": pr_id,
            "validation": validation,
            "status": new_status
        }

    def approve_human_gate(self, pr_id: str, approver: str = "Network Team Lead & Manager") -> Dict[str, Any]:
        """
        Executes human-in-the-loop sign-off for protected environments (pat / prod).
        Merges PR and launches deployment pipeline under explicit recorded authority.
        """
        pr = self.db.pull_requests.find_one({"pr_id": pr_id})
        if not pr:
            return {"error": "PR not found"}

        if pr.get("status") != "AWAITING_APPROVAL":
            return {"error": f"PR is not awaiting approval. Current status: {pr.get('status')}"}

        # Record explicit authority grant in audit log
        self.db.audit_logs.insert_one({
            "event_type": "HUMAN_APPROVAL_GRANTED",
            "agent": "HumanReviewerGate",
            "pr_id": pr_id,
            "approver": approver,
            "target_branch": pr.get("target_branch"),
            "timestamp": datetime.utcnow()
        })

        self.db.pull_requests.update_one(
            {"pr_id": pr_id},
            {"$set": {"status": "MERGED", "approved_by": approver, "updated_at": datetime.utcnow()}}
        )

        # Now trigger deployment pipeline
        deploy_res = self.run_deployment_pipeline(pr_id)
        return {
            "pr_id": pr_id,
            "approved_by": approver,
            "deployment": deploy_res,
            "status": deploy_res.get("final_status")
        }

    def abort_mid_run(self, pr_id: str, reason: str = "Operator manual intervention", aborted_by: str = "Lead SRE") -> Dict[str, Any]:
        """
        Emergency Circuit Breaker: Stops or rolls back an agent mid-run.
        """
        pr = self.db.pull_requests.find_one({"pr_id": pr_id})
        if not pr:
            return {"error": "PR not found"}

        current_status = pr.get("status")
        target_env = pr.get("target_branch")

        # If deployment was in-flight, restore prior snapshot
        deploy_rec = self.db.deployments.find_one({"pr_id": pr_id})
        rollback_msg = None
        if deploy_rec and deploy_rec.get("status") == "DEPLOYED":
            rollback_res = deployment_agent.rollback_deployment(
                deployment_id=deploy_rec["deployment_id"],
                reason=f"MID-RUN ABORT: {reason}"
            )
            rollback_msg = rollback_res.get("message")

        # Record emergency circuit breaker trip in audit log
        self.db.audit_logs.insert_one({
            "event_type": "EMERGENCY_CIRCUIT_BREAKER_TRIPPED",
            "agent": "PipelineCircuitBreaker",
            "pr_id": pr_id,
            "aborted_by": aborted_by,
            "prior_status": current_status,
            "reason": reason,
            "target_env": target_env,
            "timestamp": datetime.utcnow()
        })

        self.db.pull_requests.update_one(
            {"pr_id": pr_id},
            {
                "$set": {
                    "status": "ABORTED_MID_RUN",
                    "abort_reason": reason,
                    "aborted_by": aborted_by,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        return {
            "pr_id": pr_id,
            "status": "ABORTED_MID_RUN",
            "aborted_by": aborted_by,
            "prior_status": current_status,
            "rollback_status": rollback_msg or "Execution halted before deployment snapshot was committed."
        }

    def run_deployment_pipeline(self, pr_id: str, force_fail: bool = False) -> Dict[str, Any]:
        """
        Executes Steps 1 through 5 of the Deployment Pipeline:
        1. Deploy network policy
        2. Run synthetic network tests
        3. If test passed: attach artifact attestation
        4. If test failed: rollback change and trigger auto-remediation PR
        5. Send workflow summary & trigger audit agent
        """
        pr = self.db.pull_requests.find_one({"pr_id": pr_id})
        if not pr:
            return {"error": "PR not found"}

        target_env = pr.get("target_branch", "dev")

        # Step 1: Deploy network policy
        self.db.pull_requests.update_one({"pr_id": pr_id}, {"$set": {"status": "DEPLOYING"}})
        deploy_res = deployment_agent.deploy_policy(pr)
        deployment_id = deploy_res["deployment_id"]

        # Step 2: Run synthetic network tests
        test_res = testing_agent.run_network_tests(pr, deployment_id=deployment_id, force_fail=force_fail)

        if test_res["passed"]:
            # Step 3: Attach artifact attestation
            attestation_id = test_res["attestation"]["attestation_id"]
            final_status = "DEPLOYED"

            self.db.pull_requests.update_one(
                {"pr_id": pr_id},
                {
                    "$set": {
                        "status": final_status,
                        "deployment_result": deploy_res,
                        "test_result": test_res["test_summary"],
                        "attestation_id": attestation_id,
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            # Step 5: Audit Agent continuous verification
            audit_report = audit_agent.audit_environment(target_env)

            return {
                "final_status": final_status,
                "deployment": deploy_res,
                "tests": test_res["test_summary"],
                "attestation": test_res["attestation"],
                "audit": audit_report,
                "workflow_summary": f"PR {pr_id} successfully deployed to {target_env.upper()} with full SLSA cryptographic attestation {attestation_id}."
            }
        else:
            # Step 4: Test failed! Execute rollback and create auto-revert PR
            final_status = "ROLLED_BACK"
            rollback_res = deployment_agent.rollback_deployment(
                deployment_id=deployment_id,
                reason=f"Automated rollback: Synthetic network tests failed on {target_env.upper()}."
            )

            # Automatically trigger new PR to revert the change in Git
            revert_pr_id = f"PR-REVERT-{uuid.uuid4().hex[:6].upper()}"
            ai_rca = test_res.get("ai_remediation")
            revert_title = f"[AUTO-REVERT] Rollback failed network policy from {pr_id}"
            if ai_rca and ai_rca.get("remediation_summary"):
                revert_title = f"[AUTO-REVERT] {pr_id}: {ai_rca.get('remediation_summary')[:60]}"

            revert_pr_doc = {
                "pr_id": revert_pr_id,
                "title": revert_title,
                "author": "NetworkDeploymentAgent (Automated Remediation)",
                "target_branch": target_env,
                "source_branch": f"revert/{pr_id}",
                "policy_changes": [],
                "status": "MERGED",
                "reverts_pr_id": pr_id,
                "ai_rca": ai_rca,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            self.db.pull_requests.insert_one(revert_pr_doc)

            self.db.pull_requests.update_one(
                {"pr_id": pr_id},
                {
                    "$set": {
                        "status": final_status,
                        "deployment_result": deploy_res,
                        "test_result": test_res["test_summary"],
                        "rollback_result": rollback_res,
                        "remediation_pr_id": revert_pr_id,
                        "ai_remediation": ai_rca,
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            wf_summary = f"ALERT: PR {pr_id} failed synthetic tests on {target_env.upper()}. State was automatically rolled back to prior snapshot, remediation PR {revert_pr_id} merged, and failure episode logged into MongoDB memory."
            if ai_rca:
                wf_summary += f" [Gemini RCA: {ai_rca.get('root_cause')}]"

            return {
                "final_status": final_status,
                "deployment": deploy_res,
                "tests": test_res["test_summary"],
                "rollback": rollback_res,
                "remediation_pr_id": revert_pr_id,
                "ai_remediation": ai_rca,
                "workflow_summary": wf_summary
            }

pipeline_orchestrator = PipelineOrchestrator()
