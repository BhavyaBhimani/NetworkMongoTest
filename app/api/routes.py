from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.db.mongo import get_db
from app.db.schemas import CreatePRRequest
from app.services.pipeline import pipeline_orchestrator
from app.agents.audit_agent import audit_agent
from app.db.attestations import attestation_ledger
from app.db.memory import memory_manager
from app.db.telemetry import telemetry_store
from app.services.gemini_service import gemini_service

router = APIRouter(prefix="/api")

class HumanApprovalRequest(BaseModel):
    approver: str = "Network Team Lead & Manager"

class AbortRequest(BaseModel):
    reason: str = "Emergency operator intervention"
    aborted_by: str = "Lead SRE"

class EmergencyDriftRequest(BaseModel):
    env: str = "prod"
    reason: str = "Emergency Outage Remediation Hotfix"

@router.get("/status")
def get_system_status():
    db = get_db()
    return {
        "status": "online",
        "engine": "MongoDB Atlas" if db.is_atlas else "Embedded In-Memory MongoDB",
        "database": db.db.name,
        "llm": {
            "configured": gemini_service.is_configured,
            "model": gemini_service.model,
            "status": "Active (Gemini Free API)" if gemini_service.is_configured else "Heuristic Rule Fallback"
        },
        "collections": {
            "policies": db.policies.count_documents({}),
            "pull_requests": db.pull_requests.count_documents({}),
            "deployments": db.deployments.count_documents({}),
            "attestations": db.attestations.count_documents({}),
            "agent_memory": db.agent_memory.count_documents({}),
            "drifts": db.drifts.count_documents({}),
            "telemetry_points": db.network_telemetry.count_documents({}),
            "audit_logs": db.audit_logs.count_documents({})
        }
    }

@router.get("/llm/status")
def get_llm_status():
    return {
        "configured": gemini_service.is_configured,
        "model": gemini_service.model,
        "mode": "Gemini Cognitive Agent (Free Tier)" if gemini_service.is_configured else "Local Heuristic Rule Engine (Fallback)",
        "provider": "Google AI Studio"
    }

@router.get("/environments")
def get_environments():
    envs = ["eng", "qa", "dev", "pat", "prod"]
    result = []
    db = get_db()
    for env in envs:
        active_policies = list(db.policies.find({"target_env": env, "status": "active"}, {"_id": 0}))
        health = telemetry_store.calculate_health_aggregate(env)
        active_drift = db.drifts.find_one({"env": env, "reconciled": False}, {"_id": 0})
        result.append({
            "env": env,
            "display_name": env.upper(),
            "policy_count": len(active_policies),
            "policies": active_policies,
            "health": health,
            "has_active_drift": bool(active_drift),
            "active_drift": active_drift
        })
    return result

@router.post("/prs")
def create_pr(req: CreatePRRequest, auto_run: bool = True):
    result = pipeline_orchestrator.create_pull_request(
        title=req.title,
        author=req.author,
        target_branch=req.target_branch,
        policy_changes=req.policy_changes,
        source_branch=req.source_branch,
        auto_run=auto_run
    )
    return result

@router.get("/prs")
def list_prs(limit: int = 50):
    db = get_db()
    prs = list(db.pull_requests.find({}, {"_id": 0}).sort("created_at", -1).limit(limit))
    return prs

@router.get("/prs/{pr_id}")
def get_pr_details(pr_id: str):
    db = get_db()
    pr = db.pull_requests.find_one({"pr_id": pr_id}, {"_id": 0})
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    return pr

@router.post("/prs/{pr_id}/approve")
def approve_pr(pr_id: str, req: HumanApprovalRequest):
    result = pipeline_orchestrator.approve_human_gate(pr_id, approver=req.approver)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.post("/prs/{pr_id}/abort")
def abort_pr_mid_run(pr_id: str, req: AbortRequest):
    """
    Emergency Circuit Breaker: Stops or rolls back an agent mid-run.
    """
    result = pipeline_orchestrator.abort_mid_run(pr_id, reason=req.reason, aborted_by=req.aborted_by)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.post("/prs/{pr_id}/deploy")
def trigger_deployment(pr_id: str, force_fail: bool = False):
    result = pipeline_orchestrator.run_deployment_pipeline(pr_id, force_fail=force_fail)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/attestations")
def list_attestations(limit: int = 50):
    db = get_db()
    records = list(db.attestations.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit))
    return records

@router.get("/attestations/{attestation_id}/verify")
def verify_attestation(attestation_id: str):
    res = attestation_ledger.verify_attestation(attestation_id)
    return res

@router.get("/audit/reconstruct/{identifier}")
def reconstruct_audit_trail(identifier: str):
    """
    Hackathon Statement One Core Requirement:
    Allows a compliance reviewer to reconstruct what the agent did, why, and under whose authority.
    """
    res = attestation_ledger.reconstruct_audit_trail(identifier)
    return res

@router.get("/memory")
def get_memory_episodes(limit: int = 50):
    db = get_db()
    episodes = list(db.agent_memory.find({}, {"_id": 0}).sort("created_at", -1).limit(limit))
    return episodes

@router.get("/memory/search")
def search_memory(q: str = Query(..., description="Query for semantic vector search in MongoDB")):
    results = memory_manager.search_semantic_memory(q, limit=5, min_score=0.2)
    return results

@router.get("/telemetry/{env}")
def get_telemetry(env: str):
    metrics = telemetry_store.get_recent_metrics(env, minutes=30)
    aggregate = telemetry_store.calculate_health_aggregate(env, minutes=15)
    return {
        "env": env,
        "aggregate": aggregate,
        "recent_probes": metrics
    }

@router.post("/emergency/drift")
def simulate_emergency_drift(req: EmergencyDriftRequest):
    result = audit_agent.simulate_emergency_manual_change(
        env=req.env,
        reason=req.reason
    )
    return result

@router.get("/drifts")
def list_drifts():
    db = get_db()
    drifts = list(db.drifts.find({}, {"_id": 0}).sort("created_at", -1))
    return drifts

@router.post("/seed")
def reseed():
    from seed_data import seed_database
    seed_database()
    return {"message": "Database reseeded successfully"}
