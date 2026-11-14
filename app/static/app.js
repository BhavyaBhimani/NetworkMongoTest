// NetTrace Enterprise Policy CI/CD Console Orchestrator
let currentTab = 'prs';
let activePRId = null;
let cachedPolicies = [];
let currentEnvFilter = 'all';

document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();
    initSystemStatus();
    refreshAll();

    // Periodic live sync every 10 seconds
    setInterval(() => {
        if (currentTab === 'prs') loadPRs(false);
        if (currentTab === 'policies') loadEnvironments(false);
        if (currentTab === 'drifts') loadDrifts();
        updateSyncedTime();
    }, 10000);
});

function updateSyncedTime() {
    const el = document.getElementById('last-synced-time');
    if (el) el.innerText = `Synced ${new Date().toLocaleTimeString()}`;
}

function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('text-emerald-400', 'bg-emerald-500/10', 'border-emerald-500/20');
        btn.classList.add('text-slate-400');
    });

    const activeBtn = document.getElementById(`tab-${tab}`);
    if (activeBtn) {
        activeBtn.classList.remove('text-slate-400');
        activeBtn.classList.add('text-emerald-400', 'bg-emerald-500/10', 'border', 'border-emerald-500/20');
    }

    ['prs', 'policies', 'drifts', 'ledger'].forEach(t => {
        const el = document.getElementById(`view-${t}`);
        if (el) el.classList.toggle('hidden', t !== tab);
    });

    if (tab === 'policies') renderPoliciesTable();
    if (tab === 'drifts') loadDrifts();
    if (tab === 'ledger') loadLedger();

    lucide.createIcons();
}

async function refreshAll() {
    updateSyncedTime();
    await Promise.all([
        loadPRs(true),
        loadEnvironments(true),
        loadDrifts(),
        loadLedger()
    ]);
}

async function initSystemStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        const dbBadge = document.getElementById('db-engine-badge');
        if (dbBadge && data.engine) {
            dbBadge.innerText = data.engine.includes('Atlas') ? 'MongoDB Atlas' : 'Embedded Mongo';
        }
        const llmBadge = document.getElementById('llm-status-badge');
        if (llmBadge && data.llm) {
            llmBadge.innerText = data.llm.configured ? data.llm.model : 'Heuristic Rules';
        }
    } catch (e) {
        console.error('Failed to load status', e);
    }
}

async function loadPRs(refreshDetails = true) {
    try {
        const res = await fetch('/api/prs');
        const prs = await res.json();
        
        // Update stats
        const statPRs = document.getElementById('stat-total-prs');
        if (statPRs) statPRs.innerText = prs.length;
        const listCount = document.getElementById('pr-list-count');
        if (listCount) listCount.innerText = `${prs.length} total`;

        const container = document.getElementById('pr-list-container');
        if (!container) return;

        if (prs.length === 0) {
            container.innerHTML = `<div class="p-6 text-center text-xs text-slate-500 bg-slate-900/50 rounded-lg border border-slate-800">No pull requests found.</div>`;
            return;
        }

        container.innerHTML = prs.map(pr => {
            const isSelected = pr.pr_id === activePRId;
            const env = pr.target_branch || pr.target_env || 'dev';
            return `
                <div onclick="selectPR('${pr.pr_id}')" class="p-3.5 rounded-lg cursor-pointer transition border text-left ${isSelected ? 'bg-slate-800/90 border-emerald-500/50 shadow-sm' : 'bg-slate-900/80 border-slate-800 hover:border-slate-700'}">
                    <div class="flex items-center justify-between gap-2 mb-1.5">
                        <div class="flex items-center gap-1.5">
                            <span class="font-mono text-xs font-semibold text-white">${pr.pr_id}</span>
                            <span class="text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${getEnvBadgeClass(env)}">${env.toUpperCase()}</span>
                        </div>
                        ${getStatusPill(pr.status)}
                    </div>
                    <div class="text-xs text-slate-200 font-medium line-clamp-1">${pr.title || 'Network Policy Update'}</div>
                    <div class="flex items-center justify-between text-[11px] text-slate-400 mt-2 font-mono">
                        <span>${pr.author || 'Author'}</span>
                        <span class="text-[10px] text-slate-500">${formatTimestamp(pr.created_at || pr.updated_at)}</span>
                    </div>
                </div>
            `;
        }).join('');

        if (refreshDetails && (!activePRId || !prs.some(p => p.pr_id === activePRId))) {
            if (prs.length > 0) selectPR(prs[0].pr_id);
        } else if (activePRId) {
            const current = prs.find(p => p.pr_id === activePRId);
            if (current) renderPRDetail(current);
        }
        lucide.createIcons();
    } catch (e) {
        console.error('Failed to load PRs', e);
    }
}

async function selectPR(prId) {
    activePRId = prId;
    loadPRs(false);
    try {
        const res = await fetch(`/api/prs/${prId}`);
        const pr = await res.json();
        renderPRDetail(pr);
    } catch (e) {
        console.error('Failed to select PR', e);
    }
}

function renderPRDetail(pr) {
    const card = document.getElementById('pr-detail-card');
    if (!card) return;

    const val = pr.validation_result || {};
    const env = (pr.target_branch || pr.target_env || 'dev').toUpperCase();
    const rules = pr.policy_changes || [];

    // Human Approval Action Bar
    let humanApprovalBar = '';
    if (pr.status === 'AWAITING_APPROVAL') {
        humanApprovalBar = `
            <div class="p-4 rounded-lg bg-amber-500/10 border border-amber-500/25 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div class="space-y-0.5">
                    <div class="flex items-center gap-2 text-xs font-semibold text-amber-300">
                        <i data-lucide="shield-alert" class="w-4 h-4"></i>
                        <span>Protected Environment Review Gate</span>
                    </div>
                    <p class="text-xs text-slate-300">Target environment <strong>${env}</strong> is protected. Requires Network Team Lead / Manager sign-off before deployment.</p>
                </div>
                <div class="flex items-center gap-2 self-end sm:self-auto">
                    <button onclick="abortPR('${pr.pr_id}')" class="px-3 py-1.5 text-xs font-medium rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 hover:bg-rose-500/25 transition">
                        Reject
                    </button>
                    <button onclick="approvePR('${pr.pr_id}')" class="px-3.5 py-1.5 text-xs font-semibold rounded bg-amber-400 text-slate-950 hover:bg-amber-300 transition flex items-center gap-1.5">
                        <i data-lucide="check-circle" class="w-3.5 h-3.5"></i>
                        <span>Sign & Approve</span>
                    </button>
                </div>
            </div>
        `;
    }

    // Rules Table / Diff View
    let rulesHtml = '';
    if (rules.length === 0) {
        rulesHtml = `<div class="p-4 text-xs text-slate-500 text-center font-mono">No specific rule objects declared in payload.</div>`;
    } else {
        rulesHtml = `
            <div class="rounded-lg border border-slate-800 overflow-hidden">
                <table class="w-full text-left text-xs font-mono">
                    <thead class="bg-slate-950/60 border-b border-slate-800 text-slate-400 font-sans font-medium">
                        <tr>
                            <th class="px-3 py-2">Rule ID</th>
                            <th class="px-3 py-2">Dir</th>
                            <th class="px-3 py-2">Proto</th>
                            <th class="px-3 py-2">Port</th>
                            <th class="px-3 py-2">Source</th>
                            <th class="px-3 py-2">Destination</th>
                            <th class="px-3 py-2">Action</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800/60 bg-slate-900/60">
                        ${rules.map(r => `
                            <tr>
                                <td class="px-3 py-2 text-white font-medium">${r.rule_id || 'AUTO-RULE'}</td>
                                <td class="px-3 py-2 text-slate-400">${r.direction || 'ingress'}</td>
                                <td class="px-3 py-2 text-slate-300">${r.protocol || 'TCP'}</td>
                                <td class="px-3 py-2 text-indigo-300 font-semibold">${r.port_range || '*'}</td>
                                <td class="px-3 py-2 text-slate-400">${r.source_cidr || '0.0.0.0/0'}</td>
                                <td class="px-3 py-2 text-slate-400">${r.destination_cidr || '10.0.0.0/16'}</td>
                                <td class="px-3 py-2">
                                    <span class="text-[10px] px-1.5 py-0.5 rounded font-semibold ${(r.action || 'ALLOW') === 'ALLOW' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}">
                                        ${r.action || 'ALLOW'}
                                    </span>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    // Cognitive AI Assessment Card
    const geminiReasoning = val.gemini_reasoning;
    const recommendations = val.gemini_recommendations || [];
    const contextNotes = val.context_notes || [];
    const reasons = val.reasons || [];

    card.innerHTML = `
        <div class="space-y-5">
            <!-- Header -->
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                    <div class="flex items-center gap-2">
                        <span class="font-mono text-base font-bold text-white">${pr.pr_id}</span>
                        <span class="text-xs px-2 py-0.5 rounded font-mono font-medium ${getEnvBadgeClass(env.toLowerCase())}">${env}</span>
                        ${getStatusPill(pr.status)}
                    </div>
                    <h2 class="text-sm font-semibold text-slate-200 mt-1">${pr.title || 'Policy Modification'}</h2>
                    <div class="flex items-center gap-3 text-xs text-slate-400 mt-1 font-mono">
                        <span>Author: <strong class="text-slate-300">${pr.author}</strong></span>
                        <span>•</span>
                        <span>Risk: <strong class="${getRiskColorClass(val.risk_level)}">${val.risk_level || 'LOW'}</strong></span>
                        <span>•</span>
                        <span>Updated: ${formatTimestamp(pr.updated_at || pr.created_at)}</span>
                    </div>
                </div>

                <div class="flex items-center gap-2 self-start sm:self-center">
                    <button onclick="reconstructAudit('${pr.pr_id}')" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
                        <i data-lucide="shield" class="w-3.5 h-3.5 text-emerald-400"></i>
                        <span>Audit Trail</span>
                    </button>
                    ${pr.attestation_id ? `
                        <div class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            <i data-lucide="check-check" class="w-3.5 h-3.5"></i>
                            <span>Attested</span>
                        </div>
                    ` : ''}
                </div>
            </div>

            <!-- Lead Review Gate if Applicable -->
            ${humanApprovalBar}

            <!-- Proposed Network Policy Diffs -->
            <div class="space-y-2">
                <div class="flex items-center justify-between">
                    <h4 class="text-xs font-semibold text-slate-300 uppercase tracking-wider">Proposed Policy Rules</h4>
                    <span class="text-xs text-slate-500 font-mono">${rules.length} rule(s)</span>
                </div>
                ${rulesHtml}
            </div>

            <!-- Guardrails & Cognitive AI Evaluation Grid -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- Evaluation Guardrails Checklist -->
                <div class="p-4 rounded-lg bg-slate-950/60 border border-slate-800 space-y-2.5">
                    <h4 class="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                        <i data-lucide="check-square" class="w-3.5 h-3.5 text-emerald-400"></i>
                        <span>Policy Guardrails & Drift Gate</span>
                    </h4>
                    <div class="space-y-1.5 text-xs">
                        ${reasons.map(r => `
                            <div class="flex items-start gap-2 ${r.includes('CONFLICT') || r.includes('VIOLATION') ? 'text-rose-400' : (r.includes('RECONCILIATION') ? 'text-emerald-400' : 'text-slate-300')}">
                                <i data-lucide="${r.includes('CONFLICT') || r.includes('VIOLATION') ? 'alert-triangle' : 'check'}" class="w-3.5 h-3.5 mt-0.5 shrink-0"></i>
                                <span>${r}</span>
                            </div>
                        `).join('')}
                        ${contextNotes.map(n => `
                            <div class="text-[11px] text-slate-400 pl-5">
                                • ${n}
                            </div>
                        `).join('')}
                    </div>
                </div>

                <!-- Cognitive AI Reasoning (Gemini) -->
                <div class="p-4 rounded-lg bg-slate-950/60 border border-slate-800 space-y-2.5">
                    <div class="flex items-center justify-between">
                        <h4 class="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                            <i data-lucide="cpu" class="w-3.5 h-3.5 text-indigo-400"></i>
                            <span>Cognitive Analysis (${val.llm_model || 'gemini-3.5-flash-lite'})</span>
                        </h4>
                        <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">Vector Memory</span>
                    </div>
                    
                    <p class="text-xs text-slate-300 leading-relaxed">
                        ${geminiReasoning || 'Automated policy evaluation performed against declarative rules, active drifts, and historical incident records.'}
                    </p>

                    ${recommendations.length > 0 ? `
                        <div class="pt-2 border-t border-slate-800/80 space-y-1">
                            <span class="text-[11px] font-semibold text-slate-400">Recommendations:</span>
                            <ul class="text-[11px] text-slate-400 list-disc list-inside space-y-0.5">
                                ${recommendations.map(rec => `<li>${rec}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}
                </div>
            </div>
        </div>
    `;

    lucide.createIcons();
}

async function approvePR(prId) {
    try {
        const res = await fetch(`/api/prs/${prId}/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({approver: 'Network Lead (Human Sign-Off)'})
        });
        if (res.ok) {
            await refreshAll();
            selectPR(prId);
        } else {
            const err = await res.json();
            alert(`Approval notice: ${err.detail || 'Unable to approve'}`);
        }
    } catch (e) {
        console.error(e);
    }
}

async function abortPR(prId) {
    try {
        const res = await fetch(`/api/prs/${prId}/abort`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({reason: 'Rejected by Network Team Reviewer', aborted_by: 'Network Lead'})
        });
        if (res.ok) {
            await refreshAll();
            selectPR(prId);
        }
    } catch (e) {
        console.error(e);
    }
}

async function loadEnvironments(fetchData = true) {
    try {
        if (fetchData) {
            const res = await fetch('/api/environments');
            cachedPolicies = await res.json();
        }
        
        let totalActive = 0;
        cachedPolicies.forEach(env => {
            totalActive += (env.active_rules || []).length;
        });
        const statActive = document.getElementById('stat-active-policies');
        if (statActive) statActive.innerText = totalActive;

        renderPoliciesTable();
    } catch (e) {
        console.error('Failed to load environments', e);
    }
}

function selectEnvFilter(filter) {
    currentEnvFilter = filter;
    document.querySelectorAll('.env-filter-btn').forEach(btn => {
        btn.classList.remove('bg-slate-800', 'text-white');
        btn.classList.add('text-slate-400');
    });
    event.target.classList.remove('text-slate-400');
    event.target.classList.add('bg-slate-800', 'text-white');
    renderPoliciesTable();
}

function renderPoliciesTable() {
    const tbody = document.getElementById('policies-table-body');
    if (!tbody) return;

    let allRules = [];
    cachedPolicies.forEach(envData => {
        if (currentEnvFilter === 'all' || envData.environment === currentEnvFilter) {
            (envData.active_rules || []).forEach(r => {
                allRules.push({...r, env: envData.environment});
            });
        }
    });

    if (allRules.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-8 text-center text-xs text-slate-500 font-sans">No active policies found for selected environment.</td></tr>`;
        return;
    }

    tbody.innerHTML = allRules.map(r => `
        <tr class="hover:bg-slate-800/40 transition">
            <td class="px-4 py-2.5 text-white font-medium">${r.rule_id || 'RULE'}</td>
            <td class="px-4 py-2.5">
                <span class="text-[10px] px-1.5 py-0.5 rounded font-medium ${getEnvBadgeClass(r.env)}">${r.env.toUpperCase()}</span>
            </td>
            <td class="px-4 py-2.5 text-slate-400">${r.direction || 'ingress'}</td>
            <td class="px-4 py-2.5 text-indigo-300 font-semibold">${r.protocol || 'TCP'} / ${r.port_range || '*'}</td>
            <td class="px-4 py-2.5 text-slate-400">${r.source_cidr || '0.0.0.0/0'}</td>
            <td class="px-4 py-2.5 text-slate-400">${r.destination_cidr || '10.0.0.0/16'}</td>
            <td class="px-4 py-2.5">
                <span class="text-[10px] px-1.5 py-0.5 rounded font-semibold ${(r.action || 'ALLOW') === 'ALLOW' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}">
                    ${r.action || 'ALLOW'}
                </span>
            </td>
            <td class="px-4 py-2.5 text-slate-400 font-sans text-[11px]">${r.status || 'active'}</td>
        </tr>
    `).join('');
}

async function loadDrifts() {
    try {
        const res = await fetch('/api/drifts');
        const drifts = await res.json();
        
        const statDrifts = document.getElementById('stat-drifts');
        if (statDrifts) {
            const active = drifts.filter(d => !d.reconciled).length;
            statDrifts.innerText = active > 0 ? `${active} active` : '0 active';
            statDrifts.className = active > 0 ? 'font-mono text-base font-semibold text-rose-400' : 'font-mono text-base font-semibold text-slate-300';
        }

        const tbody = document.getElementById('drifts-table-body');
        if (!tbody) return;

        if (drifts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-xs text-slate-500 font-sans">No out-of-band drifts detected. All cloud security groups match declarative Git state.</td></tr>`;
            return;
        }

        tbody.innerHTML = drifts.map(d => {
            const rule = d.detected_rule || {};
            return `
                <tr class="hover:bg-slate-800/40 transition font-mono">
                    <td class="px-4 py-3 text-white font-medium">${d.incident_id || 'DRIFT'}</td>
                    <td class="px-4 py-3">
                        <span class="text-[10px] px-1.5 py-0.5 rounded font-medium ${getEnvBadgeClass(d.env)}">${(d.env || 'prod').toUpperCase()}</span>
                    </td>
                    <td class="px-4 py-3 text-slate-300 font-sans max-w-xs text-xs">${d.details || 'Out-of-band manual configuration'}</td>
                    <td class="px-4 py-3 text-indigo-300">${rule.protocol || 'TCP'}:${rule.port_range || '8080'} (${rule.action || 'ALLOW'})</td>
                    <td class="px-4 py-3 font-sans">
                        ${d.reconciled ? `
                            <span class="text-[10px] px-2 py-0.5 rounded font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                Reconciled via PR
                            </span>
                        ` : `
                            <span class="text-[10px] px-2 py-0.5 rounded font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
                                Active Conflict
                            </span>
                        `}
                    </td>
                    <td class="px-4 py-3 text-slate-500 text-[11px]">${formatTimestamp(d.created_at)}</td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load drifts', e);
    }
}

async function loadLedger() {
    try {
        const [resAtt, resMem] = await Promise.all([
            fetch('/api/attestations'),
            fetch('/api/memory')
        ]);
        const attestations = await resAtt.json();
        const memories = await resMem.json();

        // Update KPI
        const statAtt = document.getElementById('stat-attestations');
        if (statAtt) statAtt.innerText = attestations.length;
        const attCount = document.getElementById('attestation-count');
        if (attCount) attCount.innerText = `${attestations.length} records`;

        // Render Attestations
        const attContainer = document.getElementById('attestations-container');
        if (attContainer) {
            if (attestations.length === 0) {
                attContainer.innerHTML = `<div class="p-4 text-xs text-slate-500 text-center">No signed attestations recorded yet.</div>`;
            } else {
                attContainer.innerHTML = attestations.map(a => `
                    <div class="p-3 rounded-lg bg-slate-950/60 border border-slate-800 flex items-center justify-between text-xs font-mono">
                        <div class="space-y-0.5">
                            <div class="flex items-center gap-2">
                                <span class="font-semibold text-emerald-400">${a.attestation_id}</span>
                                <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">${a.predicate?.environment || 'dev'}</span>
                            </div>
                            <p class="text-[11px] text-slate-400 font-sans">PR: <strong class="text-white">${a.predicate?.pr_id || 'PR'}</strong> | Signed by: <span class="text-slate-300">${a.predicate?.signer || 'Pipeline'}</span></p>
                            <p class="text-[10px] text-slate-500 truncate max-w-lg">Hash: ${a.attestation_hash || 'SHA256'}</p>
                        </div>
                        <button onclick="reconstructAudit('${a.predicate?.pr_id}')" class="px-2.5 py-1 text-[11px] rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-sans transition">
                            Verify Audit
                        </button>
                    </div>
                `).join('');
            }
        }

        // Render Memory
        const memContainer = document.getElementById('memory-container');
        if (memContainer) {
            if (memories.length === 0) {
                memContainer.innerHTML = `<div class="p-4 text-xs text-slate-500 text-center">No memory episodes logged.</div>`;
            } else {
                memContainer.innerHTML = memories.map(m => `
                    <div class="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs space-y-1">
                        <div class="flex items-center justify-between">
                            <div class="flex items-center gap-2">
                                <span class="font-mono text-indigo-300 font-medium">${m.memory_id}</span>
                                <span class="text-[10px] px-1.5 py-0.5 rounded font-mono ${getEnvBadgeClass(m.environment)}">${(m.environment || 'prod').toUpperCase()}</span>
                            </div>
                            <span class="text-[10px] px-1.5 py-0.5 rounded font-semibold ${m.outcome === 'REJECTED' || m.outcome === 'OUTAGE' ? 'bg-rose-500/10 text-rose-400' : 'bg-emerald-500/10 text-emerald-400'}">
                                ${m.outcome}
                            </span>
                        </div>
                        <p class="text-slate-300 font-sans text-[11px]">${m.summary}</p>
                        <div class="flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                            <span>Ports: ${(m.affected_ports || []).join(', ') || 'N/A'}</span>
                            <span>•</span>
                            <span>CIDRs: ${(m.affected_cidrs || []).join(', ') || 'N/A'}</span>
                        </div>
                    </div>
                `).join('');
            }
        }
        lucide.createIcons();
    } catch (e) {
        console.error('Failed to load ledger', e);
    }
}

async function reconstructAudit(prId) {
    if (!prId) return;
    try {
        const res = await fetch(`/api/audit/reconstruct/${prId}`);
        const data = await res.json();
        const modal = document.getElementById('modal-audit');
        const content = document.getElementById('modal-audit-content');
        if (!modal || !content) return;

        content.innerHTML = `
            <div class="space-y-3 font-mono">
                <div class="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                    <div class="text-slate-400">Target PR: <span class="text-white font-bold">${prId}</span></div>
                    <div class="text-slate-400">Initiator: <span class="text-indigo-300">${data.identity?.initiator || 'Unknown'}</span></div>
                    <div class="text-slate-400">Environment: <span class="text-emerald-400">${data.action_executed?.target_environment || 'N/A'}</span></div>
                    <div class="text-slate-400">Cryptographic Integrity: <span class="text-emerald-400 font-bold">${data.cryptographic_attestation?.is_cryptographically_valid ? 'VERIFIED' : 'PENDING'}</span></div>
                </div>

                <div class="space-y-1">
                    <span class="text-slate-400 font-sans font-semibold">Chronological Event Trail:</span>
                    <div class="space-y-1.5 max-h-60 overflow-y-auto">
                        ${(data.chronological_event_log || []).map(evt => `
                            <div class="p-2 rounded bg-slate-950/80 border border-slate-800 text-[11px] flex items-center justify-between">
                                <span class="text-slate-300">${evt.event_type} (${evt.agent})</span>
                                <span class="text-slate-500 text-[10px]">${formatTimestamp(evt.timestamp)}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
        modal.classList.remove('hidden');
        lucide.createIcons();
    } catch (e) {
        console.error('Failed to reconstruct audit trail', e);
    }
}

function closeAuditModal() {
    const modal = document.getElementById('modal-audit');
    if (modal) modal.classList.add('hidden');
}

// Utility Helpers
function getStatusPill(status) {
    const s = (status || 'UNKNOWN').toUpperCase();
    if (s === 'MERGED' || s === 'DEPLOYED') {
        return `<span class="text-[10px] px-2 py-0.5 rounded font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">MERGED</span>`;
    }
    if (s === 'AWAITING_APPROVAL') {
        return `<span class="text-[10px] px-2 py-0.5 rounded font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">AWAITING REVIEW</span>`;
    }
    if (s === 'REJECTED') {
        return `<span class="text-[10px] px-2 py-0.5 rounded font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">REJECTED</span>`;
    }
    if (s === 'ROLLED_BACK') {
        return `<span class="text-[10px] px-2 py-0.5 rounded font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">ROLLED BACK</span>`;
    }
    return `<span class="text-[10px] px-2 py-0.5 rounded font-semibold bg-slate-800 text-slate-300">${s}</span>`;
}

function getEnvBadgeClass(env) {
    const e = (env || 'dev').toLowerCase();
    if (e === 'prod') return 'bg-rose-500/10 text-rose-400 border border-rose-500/20';
    if (e === 'pat') return 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
    if (e === 'qa') return 'bg-sky-500/10 text-sky-400 border border-sky-500/20';
    if (e === 'eng') return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
    return 'bg-slate-800 text-slate-300 border border-slate-700';
}

function getRiskColorClass(level) {
    const l = (level || 'LOW').toUpperCase();
    if (l === 'CRITICAL') return 'text-rose-400 font-bold';
    if (l === 'HIGH') return 'text-amber-400 font-semibold';
    return 'text-emerald-400';
}

function formatTimestamp(ts) {
    if (!ts) return '';
    try {
        const d = new Date(ts);
        return d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
    } catch {
        return ts;
    }
}
