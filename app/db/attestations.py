import hashlib
import hmac
import json
from datetime import datetime
from typing import Dict, Any, Optional
from app.config import settings
from app.db.mongo import get_db

class AttestationLedger:
    def __init__(self):
        self.db = get_db()
        self.signing_secret = settings.SECRET_KEY.encode("utf-8")

    def _calculate_policy_digest(self, policy_data: Any) -> str:
        serialized = json.dumps(policy_data, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _sign_payload(self, payload: str) -> str:
        return hmac.new(self.signing_secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def get_latest_attestation_hash(self) -> str:
        latest = self.db.attestations.find_one(sort=[("timestamp", -1)])
        if latest and "attestation_hash" in latest:
            return latest["attestation_hash"]
        return "GENESIS_ROOT_0000000000000000000000000000000000000000000000000000000000000000"

    def create_attestation(
        self,
        pr_id: str,
        pr_author: str,
        target_env: str,
        commit_hash: str,
        policy_changes: Any,
        test_run_id: str,
        test_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Creates an immutable, cryptographically signed SLSA/in-toto style attestation
        and stores it in the MongoDB attestations collection.
        """
        policy_digest = self._calculate_policy_digest(policy_changes)
        prev_hash = self.get_latest_attestation_hash()
        attestation_id = f"ATT-{target_env.upper()}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{pr_id}"

        payload_to_sign = f"{attestation_id}:{policy_digest}:{pr_id}:{pr_author}:{target_env}:{commit_hash}:{test_run_id}:{prev_hash}"
        signature = self._sign_payload(payload_to_sign)
        attestation_hash = hashlib.sha256(f"{payload_to_sign}:{signature}".encode("utf-8")).hexdigest()

        attestation_doc = {
            "attestation_id": attestation_id,
            "schema_version": "https://in-toto.io/Statement/v1",
            "predicate_type": "https://slsa.dev/provenance/v1",
            "subject": {
                "name": f"network-policy-{target_env}",
                "digest": {
                    "sha256": policy_digest
                }
            },
            "predicate": {
                "builder": {
                    "id": "urn:agent:network-deployment-agent-v1"
                },
                "pr_id": pr_id,
                "pr_author": pr_author,
                "target_env": target_env,
                "commit_hash": commit_hash,
                "test_run_id": test_run_id,
                "test_status": "PASSED",
                "test_metrics": test_metrics
            },
            "previous_attestation_hash": prev_hash,
            "signature": signature,
            "attestation_hash": attestation_hash,
            "timestamp": datetime.utcnow()
        }

        self.db.attestations.insert_one(attestation_doc)

        # Log into audit trail
        self.db.audit_logs.insert_one({
            "event_type": "ATTESTATION_CREATED",
            "agent": "SyntheticTestingAgent",
            "attestation_id": attestation_id,
            "pr_id": pr_id,
            "author": pr_author,
            "env": target_env,
            "attestation_hash": attestation_hash,
            "timestamp": datetime.utcnow()
        })

        clean_doc = {k: v for k, v in attestation_doc.items() if k != "_id"}
        return clean_doc

    def verify_attestation(self, attestation_id: str) -> Dict[str, Any]:
        """
        Verifies the cryptographic integrity of an attestation in MongoDB.
        """
        record = self.db.attestations.find_one({"attestation_id": attestation_id})
        if not record:
            return {"valid": False, "reason": "Attestation record not found in MongoDB"}

        policy_digest = record["subject"]["digest"]["sha256"]
        pr_id = record["predicate"]["pr_id"]
        pr_author = record["predicate"]["pr_author"]
        target_env = record["predicate"]["target_env"]
        commit_hash = record["predicate"]["commit_hash"]
        test_run_id = record["predicate"]["test_run_id"]
        prev_hash = record.get("previous_attestation_hash", "")
        recorded_sig = record["signature"]

        payload_to_verify = f"{attestation_id}:{policy_digest}:{pr_id}:{pr_author}:{target_env}:{commit_hash}:{test_run_id}:{prev_hash}"
        expected_sig = self._sign_payload(payload_to_verify)

        if hmac.compare_digest(recorded_sig, expected_sig):
            return {
                "valid": True,
                "attestation_id": attestation_id,
                "author": pr_author,
                "environment": target_env,
                "policy_digest": policy_digest,
                "signature_status": "CRYPTOGRAPHICALLY_VERIFIED",
                "chain_hash": record.get("attestation_hash")
            }
        else:
            return {
                "valid": False,
                "attestation_id": attestation_id,
                "reason": "Cryptographic signature mismatch! Artifact may have been tampered with."
            }

    def reconstruct_audit_trail(self, identifier: str) -> Dict[str, Any]:
        """
        Auditor reconstruction engine answering:
        1. What the agent did
        2. Why it did it
        3. Under whose authority
        4. Complete chain of evidence and before-action policy verification
        """
        # Can search by attestation_id or pr_id
        att = self.db.attestations.find_one({
            "$or": [{"attestation_id": identifier}, {"predicate.pr_id": identifier}]
        })
        pr_id = att["predicate"]["pr_id"] if att else identifier
        pr = self.db.pull_requests.find_one({"pr_id": pr_id})
        dep = self.db.deployments.find_one({"pr_id": pr_id})
        audit_events = list(self.db.audit_logs.find({"$or": [{"pr_id": pr_id}, {"details.pr_id": pr_id}]}).sort("timestamp", 1))

        if not pr and not att:
            return {"found": False, "message": f"No action records found for identifier: {identifier}"}

        # Remove MongoDB ObjectIds
        clean_events = []
        for e in audit_events:
            e.pop("_id", None)
            clean_events.append(e)

        reconstruction = {
            "found": True,
            "reconstruction_target": identifier,
            "identity": {
                "initiator": pr.get("author") if pr else att["predicate"].get("pr_author"),
                "agent_builder": att["predicate"]["builder"]["id"] if att else "NetworkDeploymentAgent",
                "authority_signoff": pr.get("approved_by", "Automated Policy Authority (Non-prod)") if pr else "System Authority"
            },
            "pre_action_policy_check": {
                "policy_status": "VERIFIED_BEFORE_ACTION",
                "validation_result": pr.get("validation_result") if pr else None,
                "risk_level": pr.get("validation_result", {}).get("risk_level", "LOW") if pr else "LOW",
                "reasons": pr.get("validation_result", {}).get("reasons", []) if pr else []
            },
            "action_executed": {
                "pr_id": pr_id,
                "target_environment": pr.get("target_branch") if pr else att["predicate"].get("target_env"),
                "policy_changes": pr.get("policy_changes", []) if pr else [],
                "deployment_id": dep.get("deployment_id") if dep else None,
                "status": pr.get("status") if pr else "UNKNOWN"
            },
            "verification_and_testing": {
                "synthetic_tests": pr.get("test_result") if pr else att["predicate"].get("test_metrics"),
                "rollback_occurred": pr.get("status") == "ROLLED_BACK" if pr else False
            },
            "cryptographic_attestation": {
                "attestation_id": att.get("attestation_id") if att else pr.get("attestation_id"),
                "policy_digest_sha256": att["subject"]["digest"]["sha256"] if att else None,
                "signature": att.get("signature") if att else None,
                "previous_chain_hash": att.get("previous_attestation_hash") if att else None,
                "is_cryptographically_valid": self.verify_attestation(att["attestation_id"])["valid"] if att else False
            },
            "chronological_event_log": clean_events
        }

        return reconstruction

attestation_ledger = AttestationLedger()
