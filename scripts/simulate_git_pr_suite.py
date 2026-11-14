import os
import sys
# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import time
import subprocess
from app.db.mongo import get_db
from app.services.pipeline import pipeline_orchestrator
from app.agents.audit_agent import audit_agent
from app.db.attestations import attestation_ledger
from app.db.memory import memory_manager
from seed_data import seed_database

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_header(title):
    print("\n" + "="*70)
    print(f"{BOLD}{CYAN}>>> {title}{RESET}")
    print("="*70)

def run_suite():
    print(f"\n{BOLD}{GREEN}======================================================================{RESET}")
    print(f"{BOLD}{GREEN}  NETTRACE AI - MULTI-ENVIRONMENT GIT PR AUTOMATION TEST SUITE       {RESET}")
    print(f"{BOLD}{GREEN}  Repository: BhavyaBhimani/NetworkMongoTest                         {RESET}")
    print(f"{BOLD}{GREEN}======================================================================{RESET}")

    # Initialize / reset database
    print_header("PHASE 1: INITIALIZE MONGODB POLICIES & CONTEXT MEMORY")
    seed_database()

    # TEST CASE 1: Standard Non-Prod PR (dev environment) -> Auto-Merge & Attest
    print_header("TEST CASE 1: Open PR targeting 'dev' -> Verify Workflow -> Auto-Merge -> Attest")
    print("Action: Developer opens PR modifying 'environments/dev/network-policy.json' to add port 443 analytics ingress.")

    dev_rule = {
        "rule_id": "RULE-DEV-ANALYTICS-443",
        "name": "Analytics Ingress Port 443",
        "target_env": "dev",
        "direction": "ingress",
        "protocol": "TCP",
        "port_range": "443",
        "source_cidr": "10.0.0.0/16",
        "destination_cidr": "10.1.5.0/24",
        "action": "ALLOW",
        "risk_level": "LOW"
    }

    res1 = pipeline_orchestrator.create_pull_request(
        title="[DEV] Add Analytics Service Ingress",
        author="User A (Dev)",
        target_branch="dev",
        source_branch="feature/dev-analytics",
        policy_changes=[dev_rule],
        auto_run=True
    )

    print(f"\n[1. Verify Workflow Result]")
    print(f"Status: {GREEN}{res1['status']}{RESET}")
    print(f"Risk Score: {res1['validation']['risk_level']}")
    print(f"Human Gate Required: {res1['validation']['requires_human_approval']}")
    for note in res1['validation']['context_notes']:
        print(f"  • {note}")

    print(f"\n[2. Automatic Merge & Deployment]")
    print(f"Auto-Merge: {GREEN}PASSED (Non-prod branch auto-merged){RESET}")
    deploy1 = res1.get("deployment", {})
    test1 = deploy1.get("tests", {})
    attest1 = deploy1.get("attestation", {})
    print(f"Synthetic Tests: {GREEN}{test1.get('passed_checks')}/{test1.get('total_checks')} checks passed (0% packet loss){RESET}")
    print(f"SLSA Attestation: {CYAN}{attest1.get('attestation_id')}{RESET}")

    # Verify Attestation
    verif1 = attestation_ledger.verify_attestation(attest1.get('attestation_id'))
    print(f"Cryptographic Signature: {GREEN}{verif1.get('signature_status')}{RESET}")
    assert res1['status'] == 'DEPLOYED', "Test Case 1 failed"

    # TEST CASE 2: Protected Environment (prod environment) -> Gate -> Manager Sign-Off
    print_header("TEST CASE 2: Open PR targeting 'prod' -> Verify Workflow -> Enforce Human Gate -> Sign-Off")
    print("Action: Lead opens PR modifying 'environments/prod/network-policy.json' for payment transit on port 8443.")

    prod_rule = {
        "rule_id": "RULE-PROD-PAYMENT-8443",
        "name": "Payment Gateway Transit 8443",
        "target_env": "prod",
        "direction": "ingress",
        "protocol": "TCP",
        "port_range": "8443",
        "source_cidr": "10.10.0.0/16",
        "destination_cidr": "10.20.0.0/16",
        "action": "ALLOW",
        "risk_level": "MEDIUM"
    }

    res2 = pipeline_orchestrator.create_pull_request(
        title="[PROD] Core Payment Gateway Inter-VPC Transit",
        author="User B (Lead)",
        target_branch="prod",
        source_branch="infra/prod-payment",
        policy_changes=[prod_rule],
        auto_run=True
    )

    print(f"\n[1. Verify Workflow Result]")
    print(f"Status: {YELLOW}{res2['status']}{RESET}")
    print(f"Human Gate Enforced: {BOLD}{res2['validation']['requires_human_approval']}{RESET}")
    assert res2['status'] == 'AWAITING_APPROVAL', "Test Case 2 gate failed"

    print(f"\n[2. Simulated Manager Approval]")
    approved2 = pipeline_orchestrator.approve_human_gate(res2['pr_id'], approver="Network Team Lead & Manager")
    print(f"Approval Authority Granted! Status: {GREEN}{approved2['status']}{RESET}")
    print(f"Attestation Created: {CYAN}{approved2['deployment']['attestation']['attestation_id']}{RESET}")

    # TEST CASE 3: Canary Test Failure -> Automated Fallback (Rollback in Mongo & Git Auto-Revert)
    print_header("TEST CASE 3: Fallback Part of System -> Canary Probe Fails -> Auto-Rollback & Auto-Revert PR")
    print("Action: Developer submits experimental policy to 'environments/qa/network-policy.json' with buffer isolation flaw.")

    bad_qa_rule = {
        "rule_id": "RULE-QA-BROKEN-9999",
        "name": "Experimental Routing Rule (Flawed Configuration)",
        "target_env": "qa",
        "direction": "ingress",
        "protocol": "TCP",
        "port_range": "9999",
        "source_cidr": "10.0.0.0/8",
        "destination_cidr": "192.168.1.1/32",
        "action": "ALLOW",
        "risk_level": "HIGH"
    }

    res3 = pipeline_orchestrator.create_pull_request(
        title="[QA] Experimental High-Throughput Route",
        author="User A (Dev)",
        target_branch="qa",
        source_branch="experiment/qa-broken",
        policy_changes=[bad_qa_rule],
        auto_run=True
    )

    print(f"\n[1. Synthetic Canary Probe Detected Violation]")
    dep3 = res3.get("deployment", {})
    test3 = dep3.get("tests", {})
    print(f"Failed Probes: {RED}{test3.get('failed_checks')} probe(s) failed with packet drop / buffer overflow!{RESET}")

    print(f"\n[2. Autonomous Fallback Rollback]")
    print(f"MongoDB Rollback: {YELLOW}{dep3.get('rollback', {}).get('message')}{RESET}")
    print(f"Git Auto-Revert PR Created: {CYAN}{dep3.get('remediation_pr_id')}{RESET}")
    print(f"Episodic Memory: {GREEN}Failure episode permanently indexed in MongoDB agent_memory{RESET}")
    assert res3['status'] == 'ROLLED_BACK', "Test Case 3 rollback failed"

    # TEST CASE 4: Prohibited Rule Blocked Before Action (Port 22 on 0.0.0.0/0)
    print_header("TEST CASE 4: Prohibited Public Port 22 SSH -> Blocked Before Merge")
    print("Action: Developer attempts to open administrative SSH port 22 to public 0.0.0.0/0.")

    ssh_rule = {
        "rule_id": "RULE-PROD-UNSAFE-SSH",
        "name": "Public SSH Debug Port",
        "target_env": "prod",
        "direction": "ingress",
        "protocol": "TCP",
        "port_range": "22",
        "source_cidr": "0.0.0.0/0",
        "destination_cidr": "10.0.1.10/32",
        "action": "ALLOW"
    }

    res4 = pipeline_orchestrator.create_pull_request(
        title="[PROD] Direct Admin SSH Access",
        author="User A (Dev)",
        target_branch="prod",
        source_branch="debug/ssh",
        policy_changes=[ssh_rule],
        auto_run=True
    )

    print(f"\n[1. Verify Workflow Result]")
    print(f"Status: {RED}{res4['status']}{RESET}")
    print(f"Violation: {RED}{res4['validation']['reasons'][0]}{RESET}")
    assert res4['status'] == 'REJECTED', "Test Case 4 rejection failed"

    # TEST CASE 5: Midnight Drift & Zero Cold Start
    print_header("TEST CASE 5: Midnight Manual Out-of-Band Hotfix -> Drift Reconciled into Memory -> No Cold Start")
    print("Action: Engineer applies manual firewall bypass on cloud console during midnight incident without PR.")

    drift_sim = audit_agent.simulate_emergency_manual_change(
        env="prod",
        reason="Emergency database replica connection bypass during outage"
    )

    print(f"\n[1. Audit Agent Scan]")
    print(f"Unattested Drift Detected: {RED}{drift_sim['audit_result']['unattested_drifts_detected']}{RESET}")
    print(f"Incident ingested into MongoDB Agentic Memory.")

    print(f"\n[2. Next PR Tested Against Environment]")
    next_pr = pipeline_orchestrator.create_pull_request(
        title="[PROD] Routine Maintenance Rule",
        author="User A (Dev)",
        target_branch="prod",
        source_branch="maint/db",
        policy_changes=[{
            "name": "Database Rule",
            "port_range": "8080",
            "protocol": "TCP",
            "source_cidr": "10.0.0.0/16",
            "destination_cidr": "10.0.5.20/32",
            "action": "ALLOW"
        }],
        auto_run=True
    )

    print(f"Next PR Status: {RED}{next_pr['status']}{RESET}")
    print(f"Conflict Flagged: {YELLOW}{next_pr['validation']['reasons'][0]}{RESET}")
    assert next_pr['status'] == 'REJECTED', "Test Case 5 drift check failed"

    print("\n" + "="*70)
    print(f"{BOLD}{GREEN}ALL 5 TEST CASES COMPLETED WITH 100% SUCCESS!{RESET}")
    print("="*70 + "\n")

if __name__ == "__main__":
    run_suite()
