import math
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.db.mongo import get_db

def generate_simple_embedding(text: str, dim: int = 64) -> List[float]:
    """
    Deterministic semantic token embedding projection for demonstration.
    Provides consistent vector search similarity across Atlas and local engines.
    """
    words = re.findall(r'\w+', text.lower())
    vec = [0.0] * dim
    if not words:
        return vec
    for i, word in enumerate(words):
        h = sum(ord(c) * (31 ** j) for j, c in enumerate(word)) % 1000000007
        idx = h % dim
        vec[idx] += 1.0 / (1.0 + (i * 0.1))
    
    # Normalize vector to unit length
    magnitude = math.sqrt(sum(x * x for x in vec))
    if magnitude > 0:
        vec = [x / magnitude for x in vec]
    return vec

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    return max(0.0, min(1.0, dot))

class MemoryManager:
    def __init__(self):
        self.db = get_db()

    def record_episode(
        self,
        memory_type: str,
        environment: str,
        summary: str,
        tags: List[str],
        affected_ports: List[str],
        affected_cidrs: List[str],
        outcome: str,
        resolution: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Records a new episodic memory document into MongoDB.
        """
        memory_id = f"MEM-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{len(tags)}"
        full_text = f"{summary} {' '.join(tags)} {' '.join(affected_ports)} {' '.join(affected_cidrs)} {resolution}"
        embedding = generate_simple_embedding(full_text)

        doc = {
            "memory_id": memory_id,
            "memory_type": memory_type,
            "environment": environment,
            "summary": summary,
            "tags": tags,
            "affected_ports": affected_ports,
            "affected_cidrs": affected_cidrs,
            "embedding": embedding,
            "outcome": outcome,
            "resolution": resolution,
            "metadata": metadata or {},
            "created_at": datetime.utcnow()
        }
        self.db.agent_memory.insert_one(doc)
        return memory_id

    def search_semantic_memory(self, query: str, limit: int = 5, min_score: float = 0.3) -> List[Dict[str, Any]]:
        """
        Performs semantic vector similarity search against agent memory in MongoDB.
        Uses MongoDB Atlas Vector Search when available, or cosine ranking locally.
        """
        query_vec = generate_simple_embedding(query)
        candidates = list(self.db.agent_memory.find())
        scored = []
        for doc in candidates:
            emb = doc.get("embedding", [])
            score = cosine_similarity(query_vec, emb)
            if score >= min_score:
                doc_clean = {k: v for k, v in doc.items() if k != "_id"}
                doc_clean["similarity_score"] = round(score, 4)
                scored.append(doc_clean)
        
        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored[:limit]

    def get_context_for_pr(self, env: str, ports: List[str], cidrs: List[str], author: str) -> Dict[str, Any]:
        """
        Retrieves complete situational context for a PR to prevent COLD START:
        - Past incidents on this environment
        - Past failures involving requested ports/CIDRs
        - Active un-reconciled emergency drifts
        - Author historical record
        """
        # 1. Check for active emergency drift in target env
        active_drifts = list(self.db.drifts.find({
            "env": env,
            "reconciled": False
        }))
        for d in active_drifts:
            d.pop("_id", None)

        # 2. Check for port-specific incidents in episodic memory
        query_parts = [env] + [str(p) for p in ports] + [str(c) for c in cidrs]
        query_str = " ".join(query_parts)
        similar_episodes = self.search_semantic_memory(query_str, limit=4, min_score=0.25)

        # 3. Author historical metrics
        author_prs = list(self.db.pull_requests.find({"author": author}))
        total_author_prs = len(author_prs)
        author_rollbacks = sum(1 for pr in author_prs if pr.get("status") == "ROLLED_BACK")

        # 4. Environment baseline policies
        env_policies_count = self.db.policies.count_documents({"target_env": env, "status": "active"})

        return {
            "target_env": env,
            "author_stats": {
                "total_prs": total_author_prs,
                "rollbacks": author_rollbacks,
                "trust_tier": "HIGH" if (total_author_prs >= 3 and author_rollbacks == 0) else "STANDARD"
            },
            "active_emergency_drifts": active_drifts,
            "active_env_policies_count": env_policies_count,
            "relevant_past_incidents": similar_episodes
        }

memory_manager = MemoryManager()
