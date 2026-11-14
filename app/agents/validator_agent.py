from typing import Dict, Any, List
from app.agents.base import BaseAgent
from app.db.memory import memory_manager

class PRValidatorAgent(BaseAgent):
    def __init__(self):
        super().__init__("PRValidatorAgent", "PR Policy & Context Guardrail Verifier")

    def validate_pr(self, pr_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates a Pull Request using persistent MongoDB Agentic Memory.
        Implements the 'No Cold Start' paradigm by querying past incidents,
        emergency drift states, and environment security policies.
        """
        pr_id = pr_data.get("pr_id", "PR-UNKNOWN")
        author = pr_data.get("author", "Unknown")
        target_branch = pr_data.get("target_branch", "dev").lower()
        policy_changes = pr_data.get("policy_changes", [])

        # Extract ports and CIDRs
        ports = []
        cidrs = []
        for change in policy_changes:
            p = str(change.get("port_range", "443"))
            ports.append(p)
            c = str(change.get("destination_cidr", "10.0.0.0/16"))
            cidrs.append(c)
            s_c = str(change.get("source_cidr", "10.0.0.0/16"))
            cidrs.append(s_c)

        # 1. Retrieve Situational Context from MongoDB Agentic Memory
        context = memory_manager.get_context_for_pr(
            env=target_branch,
            ports=ports,
            cidrs=cidrs,
            author=author
        )

        reasons = []
        context_notes = []
        risk_level = "LOW"
        approved = True
        requires_human_approval = False

        # 2. Check Active Emergency Drifts (Solved No-Cold-Start!)
        active_drifts = context.get("active_emergency_drifts", [])
        if active_drifts:
            approved = False
            risk_level = "HIGH"
            for d in active_drifts:
                rule_desc = d.get("detected_rule", {}).get("description", "Manual out-of-band change")
                drift_msg = f"CONFLICT: Active emergency drift {d.get('incident_id')} present in {target_branch.upper()} ('{rule_desc}'). Reconcile manual hotfix before proceeding!"
                reasons.append(drift_msg)
            context_notes.append("Audit Agent detected un-reconciled midnight hotfix in target environment.")

        # 3. Check Episodic Incident Memory for Past Outages
        past_incidents = context.get("relevant_past_incidents", [])
        matched_incidents = []
        for inc in past_incidents:
            if inc.get("similarity_score", 0) >= 0.4:
                matched_incidents.append({
                    "memory_id": inc.get("memory_id"),
                    "summary": inc.get("summary"),
                    "outcome": inc.get("outcome"),
                    "similarity": inc.get("similarity_score")
                })
                context_notes.append(
                    f"Historical Memory Warning: Similar change {inc.get('memory_id')} previously caused {inc.get('outcome')} in {inc.get('environment')}: '{inc.get('summary')}'"
                )
                if inc.get("outcome") in ["OUTAGE", "ROLLBACK"]:
                    risk_level = "HIGH"

        # 4. Enforce Dangerous Port & Open CIDR Rules
        for change in policy_changes:
            p = str(change.get("port_range", "")).strip()
            s_c = str(change.get("source_cidr", "")).strip()
            action = str(change.get("action", "ALLOW")).upper()

            if action == "ALLOW" and s_c == "0.0.0.0/0" and p in ["22", "3389", "23"]:
                approved = False
                risk_level = "CRITICAL"
                reasons.append(f"SECURITY VIOLATION: Exposing administrative port {p} to public 0.0.0.0/0 is strictly prohibited!")
            
            if action == "ALLOW" and p == "*":
                risk_level = "HIGH"
                context_notes.append("Wildcard port access detected. Requires high-privilege audit review.")

        # 5. Environment Protection Matrix (User Diagram: PAT & PROD require Network Team Lead & Manager)
        if target_branch in ["pat", "prod"]:
            requires_human_approval = True
            if approved:
                context_notes.append(
                    f"Environment '{target_branch.upper()}' is protected: Mandatory Network Team Manager and Lead approval required."
                )

        if approved and not reasons:
            reasons.append(f"All guardrail policies satisfied for {target_branch.upper()} environment.")

        # Contextual trust metric
        author_stats = context.get("author_stats", {})
        context_notes.append(
            f"Author Context: {author} (Trust Tier: {author_stats.get('trust_tier')}, Historical Rollbacks: {author_stats.get('rollbacks')})"
        )

        validation_result = {
            "approved": approved,
            "risk_level": risk_level,
            "requires_human_approval": requires_human_approval,
            "reasons": reasons,
            "context_notes": context_notes,
            "matched_historical_incidents": matched_incidents,
            "memory_context": context
        }

        self.log_event("PR_VALIDATION_COMPLETED", {
            "pr_id": pr_id,
            "author": author,
            "env": target_branch,
            "approved": approved,
            "risk_level": risk_level,
            "requires_human_approval": requires_human_approval
        })

        return validation_result

validator_agent = PRValidatorAgent()
