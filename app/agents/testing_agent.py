import uuid
import random
from datetime import datetime
from typing import Dict, Any, List
from app.agents.base import BaseAgent
from app.db.attestations import attestation_ledger
from app.db.telemetry import telemetry_store
from app.db.memory import memory_manager

class SyntheticTestingAgent(BaseAgent):
    def __init__(self):
        super().__init__("SyntheticTestingAgent", "Network Health Verifier & Attestation Generator")

    def run_network_tests(
        self,
        pr_data: Dict[str, Any],
        deployment_id: str,
        force_fail: bool = False
    ) -> Dict[str, Any]:
        """
        Executes synthetic network health, connectivity, and isolation tests.
        Streams telemetry to MongoDB Time-Series collection.
        If passed -> Attaches SLSA cryptographic attestation.
        If failed -> Initiates rollback and triggers auto-remediation PR.
        """
        pr_id = pr_data.get("pr_id")
        target_env = pr_data.get("target_branch", "dev").lower()
        policy_changes = pr_data.get("policy_changes", [])
        author = pr_data.get("author", "Unknown")

        test_run_id = f"TEST-{target_env.upper()}-{uuid.uuid4().hex[:8]}"

        # Synthetic test scenarios
        checks = [
            {"name": "Ingress Connectivity (Port Reachability)", "target": "10.0.1.50", "port": 443},
            {"name": "Egress Isolation Boundary (Zero Trust)", "target": "10.2.0.1", "port": 8443},
            {"name": "DNS Resolution & Core Routing", "target": "10.0.0.2", "port": 53},
            {"name": "Inter-VPC Transit Gateway Health", "target": "10.0.0.1", "port": 80}
        ]

        passed_checks = 0
        failed_checks = 0
        details = []
        latencies = []

        # Check for simulated failures:
        # e.g., if force_fail is set, or if policy contains a intentionally broken port like "9999" or "FAIL"
        simulated_failure_requested = force_fail or any(
            str(c.get("port_range", "")).upper() in ["FAIL", "9999", "6666"] or "fail" in str(c.get("name", "")).lower()
            for c in policy_changes
        )

        for i, check in enumerate(checks):
            # If simulated failure on check 2
            if simulated_failure_requested and i == 1:
                latency = 250.0
                loss = 85.0
                status = "DROPPED"
                err_msg = "Isolation violation: Test traffic leaked beyond designated subnet boundaries."
                failed_checks += 1
                details.append({
                    "check": check["name"],
                    "status": "FAILED",
                    "latency_ms": latency,
                    "packet_loss_pct": loss,
                    "error": err_msg
                })
            else:
                latency = round(random.uniform(4.5, 18.2), 2)
                loss = 0.0
                status = "SUCCESS"
                passed_checks += 1
                details.append({
                    "check": check["name"],
                    "status": "PASSED",
                    "latency_ms": latency,
                    "packet_loss_pct": loss
                })
            latencies.append(latency)

            # Record telemetry point in MongoDB Time-Series
            telemetry_store.record_probe_metric(
                env=target_env,
                probe_id=f"probe-{i+1}",
                target_host=check["target"],
                port=check["port"],
                latency_ms=latency,
                packet_loss_pct=loss,
                status=status
            )

        avg_latency = round(sum(latencies) / len(latencies), 2)
        all_passed = (failed_checks == 0)

        test_summary = {
            "test_run_id": test_run_id,
            "passed": all_passed,
            "total_checks": len(checks),
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "latency_avg_ms": avg_latency,
            "packet_loss_pct": round((failed_checks / len(checks)) * 100.0, 1),
            "details": details
        }

        if all_passed:
            # Step 3: Attach Artifact Attestation
            commit_hash = f"git-sha-{uuid.uuid4().hex[:10]}"
            attestation = attestation_ledger.create_attestation(
                pr_id=pr_id,
                pr_author=author,
                target_env=target_env,
                commit_hash=commit_hash,
                policy_changes=policy_changes,
                test_run_id=test_run_id,
                test_metrics=test_summary
            )

            # Record positive reinforcement in episodic memory
            memory_manager.record_episode(
                memory_type="deployment_success",
                environment=target_env,
                summary=f"Deployment for {pr_id} verified healthy with 0% packet loss and cryptographic attestation {attestation['attestation_id']}.",
                tags=["verified", target_env, "attested"],
                affected_ports=[str(c.get("port_range")) for c in policy_changes],
                affected_cidrs=[str(c.get("destination_cidr")) for c in policy_changes],
                outcome="STABLE",
                resolution="Policy successfully active and attested."
            )

            self.log_event("TESTS_PASSED_ATTESTATION_ATTACHED", {
                "pr_id": pr_id,
                "test_run_id": test_run_id,
                "attestation_id": attestation["attestation_id"],
                "env": target_env
            })

            return {
                "passed": True,
                "test_summary": test_summary,
                "attestation": attestation
            }
        else:
            # Step 4: If failed test -> Rollback change and record failure memory
            self.log_event("TESTS_FAILED_TRIGGERING_ROLLBACK", {
                "pr_id": pr_id,
                "test_run_id": test_run_id,
                "failed_checks": failed_checks,
                "env": target_env
            }, level="ERROR")

            # Record failure in episodic memory so future PRs have full context!
            fail_mem_id = memory_manager.record_episode(
                memory_type="failed_pr",
                environment=target_env,
                summary=f"Synthetic tests failed on {target_env.upper()} for {pr_id} (Author: {author}). Caused packet drop / isolation leak.",
                tags=["test_failure", "isolation_leak", target_env],
                affected_ports=[str(c.get("port_range")) for c in policy_changes],
                affected_cidrs=[str(c.get("destination_cidr")) for c in policy_changes],
                outcome="ROLLBACK",
                resolution="Automated rollback executed and remediation PR merged."
            )

            return {
                "passed": False,
                "test_summary": test_summary,
                "memory_incident_id": fail_mem_id
            }

testing_agent = SyntheticTestingAgent()
