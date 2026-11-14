import json
import logging
import re
import requests
from typing import Dict, Any, Optional, List
from app.config import settings

logger = logging.getLogger("nettrace.gemini")

def clean_json_text(text: str) -> str:
    """Cleans potential Markdown artifacts from Gemini JSON responses."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Strip accidental leading blockquotes or markdown bolding before keys
    text = re.sub(r'^[ \t]*>[ \t]*\**"?([a-zA-Z0-9_]+)"?\**[ \t]*:', r'"\1":', text, flags=re.MULTILINE)
    text = re.sub(r'^[ \t]*\**"?([a-zA-Z0-9_]+)"?\**[ \t]*:', r'"\1":', text, flags=re.MULTILINE)
    return text

class GeminiAgentService:
    """
    Google Gemini Free Tier Cognitive Agent Service.
    Integrates Gemini 1.5/2.0 Flash to provide LLM-based reasoning,
    situational risk synthesis, incident drift post-mortems, and
    automated remediation generation for NetTrace AI agents.
    """
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY.strip() if settings.GEMINI_API_KEY else ""
        self.model = settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        self.is_configured = bool(self.api_key and len(self.api_key) > 8)

    def _get_api_url(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def call_gemini(self, prompt: str, system_instruction: Optional[str] = None, json_mode: bool = True) -> Optional[str]:
        """
        Executes a REST call to Google Gemini free tier API using standard HTTP requests.
        """
        if not self.is_configured:
            return None

        url = self._get_api_url()
        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024
            }
        }

        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
            else:
                logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"Gemini API request error (falling back to local rules): {e}")

        return None

    def analyze_pr_risk(self, pr_data: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Invokes Gemini to evaluate proposed network policy changes against MongoDB
        situational context (past incidents, active emergency drifts, author trust).
        """
        if not self.is_configured:
            return None

        system_instruction = (
            "You are the NetTrace AI Cloud Security Architect and Network Policy Evaluator. "
            "You evaluate incoming PR network policy modifications against MongoDB historical incidents, "
            "active emergency drifts, and author reliability. "
            "Return valid JSON ONLY with fields: approved (bool), risk_level ('LOW'|'HIGH'|'CRITICAL'), "
            "reasoning (string), recommendations (array of strings)."
        )

        prompt = f"""
Evaluate the following Pull Request for network policy changes:

TARGET ENVIRONMENT: {pr_data.get('target_branch', 'dev').upper()}
AUTHOR: {pr_data.get('author', 'Unknown')}
POLICY CHANGES: {json.dumps(pr_data.get('policy_changes', []), indent=2, default=str)}

SITUATIONAL CONTEXT RETRIEVED FROM MONGODB (NO COLD START):
1. Active Emergency Drifts in Target Environment:
{json.dumps(context.get('active_emergency_drifts', []), indent=2, default=str)}

2. Similar Historical Incidents / Post-Mortems from Vector Memory:
{json.dumps(context.get('relevant_past_incidents', []), indent=2, default=str)}

3. Author Trust History:
{json.dumps(context.get('author_stats', {}), indent=2, default=str)}

RULES TO ENFORCE:
- If an active emergency drift exists in the target environment, the PR MUST NOT be approved until reconciled.
- Opening ports 22, 3389, or 23 to 0.0.0.0/0 is a CRITICAL security violation and MUST NOT be approved.
- Environments PAT and PROD are protected and carry higher risk.
- If past incidents show outages for the same ports or subnets, highlight the similarity and elevate risk to HIGH.

Return JSON in this exact structure:
{{
  "approved": true or false,
  "risk_level": "LOW" or "HIGH" or "CRITICAL",
  "reasoning": "Clear, concise technical analysis explaining your decision and citing relevant MongoDB context.",
  "recommendations": ["Recommendation 1", "Recommendation 2"]
}}
"""
        response_text = self.call_gemini(prompt, system_instruction=system_instruction, json_mode=True)
        if not response_text:
            return None

        try:
            return json.loads(clean_json_text(response_text))
        except Exception as e:
            logger.warning(f"Failed to parse Gemini JSON output: {e}. Raw: {response_text}")
            return None

    def synthesize_drift_incident(self, detected_rule: Dict[str, Any], env: str) -> Optional[Dict[str, Any]]:
        """
        Invokes Gemini to analyze an un-attested out-of-band firewall/router change detected
        in the cloud environment and synthesize a post-mortem incident summary for MongoDB memory.
        """
        if not self.is_configured:
            return None

        system_instruction = (
            "You are the NetTrace AI Continuous Audit Agent. "
            "Synthesize an un-attested manual cloud configuration drift into an episodic post-mortem incident "
            "to store in MongoDB Agentic Memory. Return valid JSON only."
        )

        prompt = f"""
An un-attested manual change was detected in environment: {env.upper()}
Rule details:
{json.dumps(detected_rule, indent=2, default=str)}

Generate a structured post-mortem summary for MongoDB Agentic Memory:
Return JSON:
{{
  "summary": "Concise 1-2 sentence incident summary detailing what was changed out-of-band and potential blast radius.",
  "tags": ["drift", "emergency_change", "manual_override", "{env}"],
  "root_cause_inference": "Probable reason engineer applied this hotfix manually out-of-band",
  "resolution_advice": "Recommended step to reconcile this into code before future PRs are merged"
}}
"""
        response_text = self.call_gemini(prompt, system_instruction=system_instruction, json_mode=True)
        if not response_text:
            return None

        try:
            return json.loads(clean_json_text(response_text))
        except Exception as e:
            logger.warning(f"Failed to parse Gemini drift JSON: {e}")
            return None

    def generate_remediation_analysis(
        self,
        pr_data: Dict[str, Any],
        failed_checks: List[Dict[str, Any]],
        latency_avg: float
    ) -> Optional[Dict[str, Any]]:
        """
        Invokes Gemini to analyze synthetic test failures (e.g. packet drops, isolation leaks)
        and author an intelligent remediation description for the automated rollback PR.
        """
        if not self.is_configured:
            return None

        system_instruction = (
            "You are the NetTrace AI Automated Remediation Agent. "
            "Explain network test failures and recommend exact remediation actions for an automated revert PR. "
            "Return valid JSON only."
        )

        prompt = f"""
PR {pr_data.get('pr_id')} was deployed to {pr_data.get('target_branch', 'dev').upper()} but synthetic network tests failed:
Failed Checks: {json.dumps(failed_checks, indent=2, default=str)}
Average Probe Latency: {latency_avg} ms
Policy Changes: {json.dumps(pr_data.get('policy_changes', []), indent=2, default=str)}

Generate a technical Root Cause Analysis (RCA) and remediation plan:
Return JSON:
{{
  "root_cause": "Technical explanation of why the synthetic test probes dropped traffic or leaked boundaries",
  "remediation_summary": "1-2 sentence guidance for the engineer to fix the policy in a new PR",
  "recommended_fix_steps": ["Step 1", "Step 2"]
}}
"""
        response_text = self.call_gemini(prompt, system_instruction=system_instruction, json_mode=True)
        if not response_text:
            return None

        try:
            return json.loads(clean_json_text(response_text))
        except Exception as e:
            logger.warning(f"Failed to parse Gemini remediation JSON: {e}")
            return None

gemini_service = GeminiAgentService()
