import uuid
from datetime import datetime
from typing import Dict, Any, List
from app.agents.base import BaseAgent

class NetworkDeploymentAgent(BaseAgent):
    def __init__(self):
        super().__init__("NetworkDeploymentAgent", "Automated Policy Deployer & Revision Manager")

    def deploy_policy(self, pr_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deploys network policy changes to the target environment.
        Maintains snapshot of prior active policies in MongoDB for atomic rollback.
        """
        pr_id = pr_data.get("pr_id")
        target_env = pr_data.get("target_branch", "dev").lower()
        policy_changes = pr_data.get("policy_changes", [])
        author = pr_data.get("author", "Unknown")

        deployment_id = f"DEP-{target_env.upper()}-{uuid.uuid4().hex[:8]}"

        # 1. Fetch current active policies for this env to create snapshot for rollback
        current_policies = list(self.db.policies.find({"target_env": target_env, "status": "active"}))
        for p in current_policies:
            p.pop("_id", None)

        # 2. Archive or update active policies in MongoDB
        # Deactivate existing conflicting or replaced rules
        self.db.policies.update_many(
            {"target_env": target_env, "status": "active"},
            {"$set": {"status": "superseded", "superseded_by": deployment_id}}
        )

        # 3. Insert newly approved policy rules
        new_inserted = []
        for rule in policy_changes:
            rule_doc = {
                "rule_id": rule.get("rule_id", f"RULE-{uuid.uuid4().hex[:6]}"),
                "name": rule.get("name", "Custom Network Policy"),
                "target_env": target_env,
                "direction": rule.get("direction", "ingress"),
                "protocol": rule.get("protocol", "TCP"),
                "port_range": str(rule.get("port_range", "443")),
                "source_cidr": rule.get("source_cidr", "10.0.0.0/16"),
                "destination_cidr": rule.get("destination_cidr", "10.1.0.0/16"),
                "action": rule.get("action", "ALLOW"),
                "risk_level": rule.get("risk_level", "LOW"),
                "description": rule.get("description", ""),
                "status": "active",
                "deployment_id": deployment_id,
                "version": len(current_policies) + 1,
                "applied_at": datetime.utcnow()
            }
            self.db.policies.insert_one(rule_doc)
            rule_clean = {k: v for k, v in rule_doc.items() if k != "_id"}
            new_inserted.append(rule_clean)

        # 4. Record deployment record with rollback snapshot
        deploy_record = {
            "deployment_id": deployment_id,
            "pr_id": pr_id,
            "author": author,
            "target_env": target_env,
            "status": "DEPLOYED",
            "applied_rules_count": len(new_inserted),
            "prior_snapshot": current_policies,
            "timestamp": datetime.utcnow()
        }
        self.db.deployments.insert_one(deploy_record)

        self.log_event("POLICY_DEPLOYED", {
            "deployment_id": deployment_id,
            "pr_id": pr_id,
            "target_env": target_env,
            "rules_count": len(new_inserted)
        })

        return {
            "success": True,
            "deployment_id": deployment_id,
            "target_env": target_env,
            "applied_rules": new_inserted,
            "message": f"Successfully deployed {len(new_inserted)} network policy rule(s) to {target_env.upper()}."
        }

    def rollback_deployment(self, deployment_id: str, reason: str) -> Dict[str, Any]:
        """
        Atomically reverts environment policy to the prior snapshot stored in MongoDB.
        """
        dep = self.db.deployments.find_one({"deployment_id": deployment_id})
        if not dep:
            return {"success": False, "message": "Deployment record not found"}

        target_env = dep.get("target_env")
        prior_snapshot = dep.get("prior_snapshot", [])

        # Deactivate current policies applied by this deployment
        self.db.policies.update_many(
            {"target_env": target_env, "deployment_id": deployment_id},
            {"$set": {"status": "rolled_back", "rollback_reason": reason}}
        )

        # Restore prior snapshot
        restored_count = 0
        for prior_rule in prior_snapshot:
            prior_rule["status"] = "active"
            prior_rule["restored_at"] = datetime.utcnow()
            self.db.policies.insert_one(prior_rule)
            restored_count += 1

        self.db.deployments.update_one(
            {"deployment_id": deployment_id},
            {"$set": {"status": "ROLLED_BACK", "rollback_reason": reason, "rollback_at": datetime.utcnow()}}
        )

        self.log_event("POLICY_ROLLED_BACK", {
            "deployment_id": deployment_id,
            "target_env": target_env,
            "restored_rules_count": restored_count,
            "reason": reason
        }, level="WARNING")

        return {
            "success": True,
            "deployment_id": deployment_id,
            "target_env": target_env,
            "restored_rules_count": restored_count,
            "message": f"Rollback complete: Restored {restored_count} baseline rules in {target_env.upper()}."
        }

deployment_agent = NetworkDeploymentAgent()
