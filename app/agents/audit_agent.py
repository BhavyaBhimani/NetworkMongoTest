import uuid
from datetime import datetime
from typing import Dict, Any, List
from app.agents.base import BaseAgent
from app.db.attestations import attestation_ledger
from app.db.memory import memory_manager
from app.services.gemini_service import gemini_service

class AuditReconciliationAgent(BaseAgent):
    def __init__(self):
        super().__init__("AuditReconciliationAgent", "Continuous Drift Auditor & Memory Synchronizer")

    def audit_environment(self, env: str) -> Dict[str, Any]:
        """
        Audits active environment policies against cryptographic attestations in MongoDB.
        Detects un-attested manual changes (e.g. emergency hotfix done out-of-band).
        Updates MongoDB Agentic Memory to ensure NO COLD START for future agents.
        """
        active_policies = list(self.db.policies.find({"target_env": env, "status": "active"}))
        unattested_rules = []
        verified_attestations = []

        for policy in active_policies:
            policy_id = policy.get("rule_id")
            deployment_id = policy.get("deployment_id")

            if not deployment_id:
                # Rule was created manually or via emergency bypass without PR deployment!
                unattested_rules.append(policy)
                continue

            # Look for attestation linked to deployment's PR
            dep = self.db.deployments.find_one({"deployment_id": deployment_id})
            pr_id = dep.get("pr_id") if dep else None
            attestation = self.db.attestations.find_one({"predicate.pr_id": pr_id}) if pr_id else None

            if not attestation:
                unattested_rules.append(policy)
            else:
                # Verify cryptographic signature
                verification = attestation_ledger.verify_attestation(attestation.get("attestation_id"))
                verified_attestations.append(verification)

        # Reconcile un-attested rules if any
        drift_incidents = []
        for rule in unattested_rules:
            incident_id = f"DRIFT-{env.upper()}-{uuid.uuid4().hex[:6]}"
            incident_doc = {
                "incident_id": incident_id,
                "env": env,
                "drift_type": "UNATTESTED_MANUAL_CHANGE",
                "detected_rule": rule,
                "detected_by": self.agent_name,
                "reconciled": False,
                "details": f"Out-of-band manual configuration detected for rule '{rule.get('name', 'Unknown')}' on port {rule.get('port_range')} without PR attestation.",
                "created_at": datetime.utcnow()
            }
            # Only insert if not already recorded
            if not self.db.drifts.find_one({"env": env, "detected_rule.rule_id": rule.get("rule_id"), "reconciled": False}):
                self.db.drifts.insert_one(incident_doc)
                drift_incidents.append(incident_doc)

                # UPDATE AGENTIC MEMORY (Crucial: Solves Hackathon "No Cold Start" Problem!)
                summary_text = f"Emergency manual change detected on {env.upper()}: Rule '{rule.get('name')}' opened port {rule.get('port_range')} out-of-band without PR pipeline."
                tags = ["drift", "emergency_change", "manual_override", env]
                resolution_text = "Audit agent recorded manual drift; flagged for upcoming PR reconciliation."
                llm_used = False

                if gemini_service.is_configured:
                    synth = gemini_service.synthesize_drift_incident(rule, env)
                    if synth:
                        summary_text = synth.get("summary", summary_text)
                        tags = synth.get("tags", tags)
                        resolution_text = synth.get("resolution_advice", resolution_text)
                        llm_used = True

                mem_id = memory_manager.record_episode(
                    memory_type="manual_drift",
                    environment=env,
                    summary=summary_text,
                    tags=tags,
                    affected_ports=[str(rule.get("port_range", ""))],
                    affected_cidrs=[str(rule.get("destination_cidr", ""))],
                    outcome="EMERGENCY_OVERRIDE",
                    resolution=resolution_text,
                    metadata={"incident_id": incident_id, "rule_id": rule.get("rule_id"), "llm_synthesized": llm_used}
                )

                self.log_event("DRIFT_DETECTED_MEMORY_UPDATED", {
                    "incident_id": incident_id,
                    "env": env,
                    "memory_id": mem_id,
                    "rule": rule.get("name"),
                    "llm_synthesized": llm_used
                }, level="WARNING")

        return {
            "environment": env,
            "total_active_rules": len(active_policies),
            "verified_rules_count": len(verified_attestations),
            "unattested_drifts_detected": len(drift_incidents),
            "drifts": drift_incidents,
            "attestations": verified_attestations
        }

    def simulate_emergency_manual_change(
        self,
        env: str,
        reason: str = "Outage remediation hotfix"
    ) -> Dict[str, Any]:
        """
        Simulates an engineer logging directly into cloud router/console during a 3 AM incident
        and applying an un-attested firewall rule.
        The Audit Agent immediately reconciles this into MongoDB Memory.
        """
        emergency_rule_id = f"EMERG-RULE-{uuid.uuid4().hex[:6]}"
        emergency_rule = {
            "rule_id": emergency_rule_id,
            "name": f"Emergency Hotfix ({reason})",
            "target_env": env,
            "direction": "ingress",
            "protocol": "TCP",
            "port_range": "8080",
            "source_cidr": "0.0.0.0/0",
            "destination_cidr": "10.0.5.20/32",
            "action": "ALLOW",
            "risk_level": "HIGH",
            "description": f"Applied out-of-band directly to cloud security group: {reason}",
            "status": "active",
            "deployment_id": None,  # Bypassed PR deployment!
            "applied_at": datetime.utcnow()
        }
        self.db.policies.insert_one(emergency_rule)

        # Audit agent detects it and syncs memory
        audit_result = self.audit_environment(env)
        return {
            "simulated_rule": emergency_rule,
            "audit_result": audit_result
        }

audit_agent = AuditReconciliationAgent()
