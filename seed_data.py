import sys
from datetime import datetime, timedelta
from app.db.mongo import get_db
from app.db.memory import memory_manager
from app.db.attestations import attestation_ledger
from app.db.telemetry import telemetry_store

def seed_database():
    db = get_db()
    print("Initializing NetTrace AI Database Seeder...")

    # Clear existing data for fresh clean demo state
    db.policies.delete_many({})
    db.pull_requests.delete_many({})
    db.deployments.delete_many({})
    db.attestations.delete_many({})
    db.agent_memory.delete_many({})
    db.network_telemetry.delete_many({})
    db.drifts.delete_many({})
    db.audit_logs.delete_many({})

    print("Cleared existing test collections.")

    # 1. Seed Baseline Network Policies across branches
    environments = ["eng", "qa", "dev", "pat", "prod"]
    for env in environments:
        rules = [
            {
                "rule_id": f"BASE-HTTP-{env.upper()}",
                "name": f"Core HTTPS Ingress ({env})",
                "target_env": env,
                "direction": "ingress",
                "protocol": "TCP",
                "port_range": "443",
                "source_cidr": "10.0.0.0/8",
                "destination_cidr": "10.1.0.0/16",
                "action": "ALLOW",
                "risk_level": "LOW",
                "description": "Standard encrypted web ingress from internal enterprise network",
                "status": "active",
                "version": 1,
                "applied_at": datetime.utcnow() - timedelta(days=30)
            },
            {
                "rule_id": f"BASE-DNS-{env.upper()}",
                "name": f"Core DNS Egress ({env})",
                "target_env": env,
                "direction": "egress",
                "protocol": "UDP",
                "port_range": "53",
                "source_cidr": "10.1.0.0/16",
                "destination_cidr": "1.1.1.1/32",
                "action": "ALLOW",
                "risk_level": "LOW",
                "description": "Resolver routing for authoritative internal DNS queries",
                "status": "active",
                "version": 1,
                "applied_at": datetime.utcnow() - timedelta(days=30)
            }
        ]
        db.policies.insert_many(rules)

    print(f"Seeded baseline policies across {len(environments)} environments.")

    # 2. Seed Genesis Attestation in MongoDB
    genesis_attestation = attestation_ledger.create_attestation(
        pr_id="PR-GENESIS-001",
        pr_author="Cloud Infrastructure Architect",
        target_env="prod",
        commit_hash="c0ffee9812734612847",
        policy_changes=[{"name": "Genesis Baseline Policy"}],
        test_run_id="TEST-INIT-001",
        test_metrics={"passed": True, "total_checks": 4, "passed_checks": 4, "failed_checks": 0}
    )
    print(f"Created Genesis Attestation: {genesis_attestation['attestation_id']}")

    # 3. Seed Historical Episodic Memory in MongoDB (Crucial for Context & No Cold Start)
    memory_manager.record_episode(
        memory_type="incident",
        environment="prod",
        summary="Critical Outage: Unauthorized public SSH port 22 exposed to 0.0.0.0/0 on production payment cluster. Influx of unauthorized port sweeps detected.",
        tags=["outage", "security_breach", "port_22", "ssh", "prod"],
        affected_ports=["22"],
        affected_cidrs=["0.0.0.0/0"],
        outcome="OUTAGE",
        resolution="Emergency rollback executed. Policy guardrail permanently updated to prohibit port 22."
    )

    memory_manager.record_episode(
        memory_type="failed_pr",
        environment="pat",
        summary="Staging Regression: PR attempting wildcard port route 9999 caused transit gateway buffer overflow and synthetic isolation test failure.",
        tags=["isolation_leak", "buffer_overflow", "pat", "staging"],
        affected_ports=["9999", "*"],
        affected_cidrs=["10.2.0.0/16"],
        outcome="ROLLBACK",
        resolution="Automated rollback restored pre-acceptance baseline."
    )

    memory_manager.record_episode(
        memory_type="manual_drift",
        environment="qa",
        summary="Midnight Hotfix: Out-of-band firewall bypass applied directly to cloud console for port 8080 during microservice latency degradation.",
        tags=["drift", "emergency_change", "port_8080", "qa"],
        affected_ports=["8080"],
        affected_cidrs=["10.0.5.0/24"],
        outcome="EMERGENCY_OVERRIDE",
        resolution="Audit agent recorded manual drift; flagged for PR reconciliation."
    )

    print("Seeded historical episodic memories into MongoDB.")

    # 4. Seed Historical Telemetry in Time-Series Collection
    now = datetime.utcnow()
    for env in environments:
        for offset in range(20, 0, -2):
            ts = now - timedelta(minutes=offset)
            telemetry_store.record_probe_metric(
                env=env,
                probe_id="probe-ingress-1",
                target_host="10.0.1.50",
                port=443,
                latency_ms=10.0 + (offset % 5),
                packet_loss_pct=0.0,
                status="SUCCESS",
                timestamp=ts
            )
            telemetry_store.record_probe_metric(
                env=env,
                probe_id="probe-egress-2",
                target_host="10.2.0.1",
                port=8443,
                latency_ms=14.0 + (offset % 4),
                packet_loss_pct=0.0,
                status="SUCCESS",
                timestamp=ts
            )

    print("Seeded realistic network telemetry time-series.")
    print("Database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
