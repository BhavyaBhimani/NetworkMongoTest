// NetTrace AI Frontend Orchestrator
let currentTab = 'prs';
let telemetryChart = null;
let activePRId = null;

document.addEventListener('DOMContentLoaded', () => {
    lucide.createIcons();
    initSystemStatus();
    loadPRs();
    loadEnvironments();
    loadMemory();
    loadAttestations();
    loadDrifts();

    // Auto refresh every 8 seconds
    setInterval(() => {
        if (currentTab === 'prs') loadPRs(false);
        if (currentTab === 'environments') loadEnvironments(false);
    }, 8000);
});

function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('bg-mongo-green/10', 'text-mongo-green', 'border', 'border-mongo-green/30');
        btn.classList.add('text-slate-400');
    });

    const activeBtn = document.getElementById(`tab-${tab}`);
    if (activeBtn) {
        activeBtn.classList.remove('text-slate-400');
        activeBtn.classList.add('bg-mongo-green/10', 'text-mongo-green', 'border', 'border-mongo-green/30');
    }

    ['prs', 'environments', 'memory', 'attestations', 'audit'].forEach(t => {
        const el = document.getElementById(`view-${t}`);
        if (el) el.classList.toggle('hidden', t !== tab);
    });

    if (tab === 'environments') {
        setTimeout(initTelemetryChart, 150);
    }
    if (tab === 'memory') loadMemory();
    if (tab === 'attestations') loadAttestations();
    if (tab === 'audit') loadDrifts();

    lucide.createIcons();
}

async function initSystemStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        const badge = document.getElementById('db-engine-badge');
        if (badge) {
            badge.innerText = data.engine;
            badge.className = data.engine.includes('Atlas')
                ? 'text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 font-mono border border-emerald-800'
                : 'text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono border border-slate-700';
        }
        const llmBadge = document.getElementById('llm-status-badge');
        if (llmBadge && data.llm) {
            if (data.llm.configured) {
                llmBadge.innerText = `✨ ${data.llm.model} (Active)`;
                llmBadge.className = 'text-[10px] px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 font-mono border border-indigo-700 shadow-sm shadow-indigo-500/20';
            } else {
                llmBadge.innerText = 'Local Heuristic Rules';
                llmBadge.className = 'text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-mono border border-slate-700';
            }
        }
    } catch (e) {
        console.error('Failed to get status', e);
    }
}

async function loadPRs(refreshDetails = true) {
    try {
        const res = await fetch('/api/prs');
        const prs = await res.json();
        const container = document.getElementById('pr-list-container');
        const badge = document.getElementById('pr-count-badge');
        if (badge) badge.innerText = prs.length;

        if (!container) return;
        if (prs.length === 0) {
            container.innerHTML = `<div class="p-4 rounded-lg bg-slate-900 border border-slate-800 text-center text-xs text-slate-500">No PRs found. Run a scenario above.</div>`;
            return;
        }

        container.innerHTML = prs.map(pr => {
            const isSelected = pr.pr_id === activePRId;
            const statusBadge = getStatusBadge(pr.status);
            return `
                <div onclick="selectPR('${pr.pr_id}')" class="p-3.5 rounded-xl cursor-pointer transition border ${isSelected ? 'bg-slate-800/90 border-mongo-green/60 shadow-md' : 'bg-mongo-card/70 border-mongo-border hover:border-slate-600'}">
                    <div class="flex items-center justify-between gap-2 mb-1.5">
                        <div class="flex items-center gap-1.5">
                            <span class="font-mono text-xs font-bold text-white">${pr.pr_id}</span>
                            <span class="text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${getEnvBadgeClass(pr.target_branch)}">${pr.target_branch}</span>
                        </div>
                        ${statusBadge}
                    </div>
                    <div class="text-xs text-slate-200 font-medium line-clamp-1">${pr.title}</div>
                    <div class="flex items-center justify-between text-[11px] text-slate-400 mt-2">
                        <span>${pr.author}</span>
                        <span class="font-mono text-[10px]">${new Date(pr.created_at).toLocaleTimeString()}</span>
                    </div>
                </div>
            `;
        }).join('');

        if (refreshDetails && (!activePRId || !prs.some(p => p.pr_id === activePRId))) {
            if (prs.length > 0) selectPR(prs[0].pr_id);
        } else if (activePRId) {
            const current = prs.find(p => p.pr_id === activePRId);
            if (current) renderPRDetails(current);
        }
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
        renderPRDetails(pr);
    } catch (e) {
        console.error(e);
    }
}

function renderPRDetails(pr) {
    const card = document.getElementById('pr-details-card');
    if (!card) return;

    const val = pr.validation_result;
    const test = pr.test_result;

    let humanApprovalBtn = '';
    if (pr.status === 'AWAITING_APPROVAL') {
        humanApprovalBtn = `
            <div class="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-between gap-4 mt-4">
                <div>
                    <h4 class="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                        <i data-lucide="shield-alert" class="w-4 h-4"></i>
                        <span>Mandatory Pre-Action Authority Gate</span>
                    </h4>
                    <p class="text-[11px] text-slate-300 mt-0.5">Protected branch <strong>${pr.target_branch.toUpperCase()}</strong> requires Network Team Lead & Manager sign-off before action runs.</p>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="abortPRMidRun('${pr.pr_id}')" class="px-3 py-2 text-xs font-bold rounded-lg bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 transition">
                        Reject / Abort
                    </button>
                    <button onclick="approvePRGate('${pr.pr_id}')" class="px-4 py-2 text-xs font-bold rounded-lg bg-amber-400 text-black hover:bg-amber-300 transition flex items-center gap-1.5 shadow-md">
                        <i data-lucide="check" class="w-4 h-4"></i>
                        <span>Approve Authority</span>
                    </button>
                </div>
            </div>
        `;
    }

    card.innerHTML = `
        <div class="space-y-5">
            <!-- Header -->
            <div class="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-mongo-border pb-4">
                <div>
                    <div class="flex items-center gap-2">
                        <span class="font-mono text-base font-bold text-white">${pr.pr_id}</span>
                        <span class="text-xs px-2 py-0.5 rounded font-mono font-medium ${getEnvBadgeClass(pr.target_branch)}">${pr.target_branch}</span>
                        ${getStatusBadge(pr.status)}
                    </div>
                    <h2 class="text-sm font-semibold text-slate-200 mt-1">${pr.title}</h2>
                    <p class="text-xs text-slate-400 mt-0.5">Initiator: <strong class="text-slate-300">${pr.author}</strong> | Authority: <span class="text-indigo-300 font-medium">${pr.approved_by || 'Auto-Evaluated Policy'}</span></p>
                </div>

                <div class="flex items-center gap-2">
                    <button onclick="reconstructAudit('${pr.pr_id}')" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-500/10 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/20 transition">
                        <i data-lucide="history" class="w-3.5 h-3.5"></i>
                        <span>Reconstruct Audit Trail</span>
                    </button>
                    ${pr.attestation_id ? `
                        <button onclick="inspectAttestation('${pr.attestation_id}')" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded-lg bg-emerald-500/10 text-mongo-green border border-mongo-green/30 hover:bg-emerald-500/20 transition">
                            <i data-lucide="key" class="w-3.5 h-3.5"></i>
                            <span>${pr.attestation_id.substring(0, 16)}...</span>
                        </button>
                    ` : ''}
                </div>
            </div>

            ${humanApprovalBtn}

            <!-- Multi-Agent Pipeline Execution Stage Cards -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <!-- Validation Agent Card -->
                <div class="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2.5">
                    <div class="flex items-center justify-between">
                        <h4 class="text-xs font-bold text-cyan-400 flex items-center gap-1.5">
                            <i data-lucide="cpu" class="w-3.5 h-3.5"></i>
                            <span>Pre-Action Policy Gate (Enforced Before Run)</span>
                        </h4>
                        <div class="flex items-center gap-1.5">
                            ${val?.llm_assisted ? `<span class="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-indigo-950 text-indigo-300 border border-indigo-700">✨ Gemini</span>` : ''}
                            <span class="text-[10px] px-2 py-0.5 rounded font-mono font-semibold ${val?.risk_level === 'CRITICAL' ? 'bg-rose-950 text-rose-400 border border-rose-800' : (val?.risk_level === 'HIGH' ? 'bg-amber-950 text-amber-400 border border-amber-800' : 'bg-emerald-950 text-emerald-400 border border-emerald-800')}">Risk: ${val?.risk_level || 'N/A'}</span>
                        </div>
                    </div>

                    ${val ? `
                        <div class="space-y-1.5 text-xs">
                            <div class="text-[11px] text-slate-300">${val.reasons?.join('<br>') || 'Validated.'}</div>
                            ${val.gemini_recommendations && val.gemini_recommendations.length ? `
                                <div class="mt-2 p-2 rounded bg-indigo-950/40 border border-indigo-900/60 text-[11px] text-indigo-200 space-y-1">
                                    <span class="text-indigo-400 font-semibold block text-[10px] uppercase tracking-wider flex items-center gap-1">
                                        <i data-lucide="sparkles" class="w-3 h-3"></i> Gemini AI Recommendations:
                                    </span>
                                    ${val.gemini_recommendations.map(r => `<div class="flex items-start gap-1"><span class="text-indigo-400">→</span><span>${r}</span></div>`).join('')}
                                </div>
                            ` : ''}
                            ${val.context_notes?.length ? `
                                <div class="mt-2 p-2 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-400 space-y-1">
                                    <span class="text-indigo-300 font-semibold block text-[10px] uppercase tracking-wider">Retrieved MongoDB Context:</span>
                                    ${val.context_notes.map(n => `<div class="flex items-start gap-1"><span class="text-mongo-green">•</span><span>${n}</span></div>`).join('')}
                                </div>
                            ` : ''}
                        </div>
                    ` : '<div class="text-xs text-slate-500">Awaiting validation trigger...</div>'}
                </div>

                <!-- Synthetic Testing & Attestation Card -->
                <div class="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2.5">
                    <div class="flex items-center justify-between">
                        <h4 class="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                            <i data-lucide="activity" class="w-3.5 h-3.5"></i>
                            <span>Post-Action Verification & Rollback Sentinel</span>
                        </h4>
                        <span class="text-[10px] font-mono text-slate-400">${test ? `${test.passed_checks}/${test.total_checks} passed` : 'Pending'}</span>
                    </div>

                    ${test ? `
                        <div class="space-y-2 text-xs">
                            <div class="flex items-center justify-between text-[11px] text-slate-300">
                                <span>Avg Latency: <strong class="text-white">${test.latency_avg_ms} ms</strong></span>
                                <span>Packet Loss: <strong class="${test.packet_loss_pct > 0 ? 'text-rose-400' : 'text-emerald-400'}">${test.packet_loss_pct}%</strong></span>
                            </div>
                            ${test.ai_remediation ? `
                                <div class="p-2 rounded bg-rose-950/40 border border-rose-900/60 text-[11px] text-rose-200 space-y-1">
                                    <span class="text-rose-400 font-semibold block text-[10px] uppercase tracking-wider flex items-center gap-1">
                                        <i data-lucide="sparkles" class="w-3 h-3"></i> Gemini Root Cause Analysis:
                                    </span>
                                    <p>${test.ai_remediation.root_cause}</p>
                                    <p class="text-slate-300 text-[10px] mt-1"><strong>Fix:</strong> ${test.ai_remediation.remediation_summary}</p>
                                </div>
                            ` : ''}
                            <div class="space-y-1 mt-1">
                                ${test.details.map(d => `
                                    <div class="flex items-center justify-between p-1.5 rounded bg-slate-950 border border-slate-800/80 text-[10px]">
                                        <span class="text-slate-300">${d.check}</span>
                                        <span class="font-mono font-semibold ${d.status === 'PASSED' ? 'text-emerald-400' : 'text-rose-400'}">${d.status} (${d.latency_ms}ms)</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : '<div class="text-xs text-slate-500">Tests run automatically after deployment.</div>'}
                </div>
            </div>

            <!-- Policy Diffs -->
            <div class="p-4 rounded-xl bg-slate-950 border border-slate-800/90 space-y-2">
                <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                    <i data-lucide="file-diff" class="w-3.5 h-3.5 text-mongo-green"></i>
                    <span>Network Policy Rules Requested in this PR</span>
                </h4>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs font-mono">
                        <thead class="text-slate-500 border-b border-slate-800 text-[11px]">
                            <tr>
                                <th class="pb-1.5">Name</th>
                                <th class="pb-1.5">Port</th>
                                <th class="pb-1.5">Proto</th>
                                <th class="pb-1.5">Source CIDR</th>
                                <th class="pb-1.5">Action</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800 text-slate-300 text-[11px]">
                            ${pr.policy_changes?.map(p => `
                                <tr>
                                    <td class="py-1.5">${p.name || 'Rule'}</td>
                                    <td class="py-1.5 text-amber-300 font-bold">${p.port_range}</td>
                                    <td class="py-1.5">${p.protocol}</td>
                                    <td class="py-1.5 text-indigo-300">${p.source_cidr}</td>
                                    <td class="py-1.5 font-bold ${p.action === 'ALLOW' ? 'text-emerald-400' : 'text-rose-400'}">${p.action}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="5" class="py-2 text-slate-500">No policy diffs.</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;

    lucide.createIcons();
}

function getStatusBadge(status) {
    switch (status) {
        case 'DEPLOYED':
            return '<span class="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">DEPLOYED</span>';
        case 'ROLLED_BACK':
            return '<span class="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-rose-950 text-rose-400 border border-rose-800">ROLLED_BACK</span>';
        case 'ABORTED_MID_RUN':
            return '<span class="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-purple-950 text-purple-300 border border-purple-800">ABORTED_MID_RUN</span>';
        case 'AWAITING_APPROVAL':
            return '<span class="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-amber-950 text-amber-400 border border-amber-800 animate-pulse">AWAITING APPROVAL</span>';
        case 'REJECTED':
            return '<span class="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-rose-950 text-rose-400 border border-rose-800">REJECTED</span>';
        case 'VALIDATING':
        case 'DEPLOYING':
            return `<span class="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800 animate-pulse">${status}</span>`;
        default:
            return `<span class="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-slate-800 text-slate-300 border border-slate-700">${status}</span>`;
    }
}

function getEnvBadgeClass(env) {
    switch (env?.toLowerCase()) {
        case 'prod': return 'bg-rose-950 text-rose-300 border border-rose-800';
        case 'pat': return 'bg-amber-950 text-amber-300 border border-amber-800';
        case 'qa': return 'bg-purple-950 text-purple-300 border border-purple-800';
        case 'eng': return 'bg-blue-950 text-blue-300 border border-blue-800';
        default: return 'bg-indigo-950 text-indigo-300 border border-indigo-800';
    }
}

// Scenarios Launcher
async function runScenario(scenarioKey) {
    let payload = {};
    if (scenarioKey === 'safe_dev') {
        payload = {
            title: "Enable Ingress HTTPS for Analytics Engine",
            author: "User A (Dev)",
            target_branch: "dev",
            source_branch: "feature/analytics-ingress",
            policy_changes: [{
                name: "Analytics Service Ingress",
                port_range: "443",
                protocol: "TCP",
                source_cidr: "10.0.0.0/16",
                destination_cidr: "10.1.5.0/24",
                action: "ALLOW",
                risk_level: "LOW"
            }]
        };
    } else if (scenarioKey === 'prod_gate') {
        payload = {
            title: "Core Payment Gateway Inter-VPC Transit",
            author: "User B (Lead)",
            target_branch: "prod",
            source_branch: "infra/payment-transit",
            policy_changes: [{
                name: "PCI-DSS Compliant Transit",
                port_range: "8443",
                protocol: "TCP",
                source_cidr: "10.10.0.0/16",
                destination_cidr: "10.20.0.0/16",
                action: "ALLOW",
                risk_level: "MEDIUM"
            }]
        };
    } else if (scenarioKey === 'fail_rollback') {
        payload = {
            title: "Experimental Routing Rule (Flawed Configuration)",
            author: "User A (Dev)",
            target_branch: "qa",
            source_branch: "experiment/flawed-routing",
            policy_changes: [{
                name: "Broken Gateway Rule (Simulated Fail)",
                port_range: "9999",
                protocol: "TCP",
                source_cidr: "10.0.0.0/8",
                destination_cidr: "192.168.1.1/32",
                action: "ALLOW",
                risk_level: "HIGH"
            }]
        };
    } else if (scenarioKey === 'unsafe_ssh') {
        payload = {
            title: "Direct Admin SSH Access for Debugging",
            author: "User A (Dev)",
            target_branch: "prod",
            source_branch: "debug/ssh-access",
            policy_changes: [{
                name: "Open SSH Port 22 to Public",
                port_range: "22",
                protocol: "TCP",
                source_cidr: "0.0.0.0/0",
                destination_cidr: "10.0.1.10/32",
                action: "ALLOW",
                risk_level: "CRITICAL"
            }]
        };
    }

    try {
        const res = await fetch('/api/prs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        activePRId = result.pr_id;
        await loadPRs();
        selectPR(result.pr_id);
    } catch (e) {
        console.error(e);
    }
}

async function approvePRGate(prId) {
    try {
        const res = await fetch(`/api/prs/${prId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approver: "Network Team Lead & Manager" })
        });
        const data = await res.json();
        await loadPRs();
        selectPR(prId);
    } catch (e) {
        console.error(e);
    }
}

async function abortPRMidRun(prId) {
    const reason = prompt("Enter reason for emergency mid-run abort:", "Manual operator emergency circuit breaker trip");
    if (!reason) return;

    try {
        const res = await fetch(`/api/prs/${prId}/abort`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: reason, aborted_by: "Lead SRE" })
        });
        const data = await res.json();
        alert(`Pipeline aborted mid-run!\nRollback status: ${data.rollback_status}`);
        await loadPRs();
        selectPR(prId);
    } catch (e) {
        console.error(e);
    }
}

// Environments View
async function loadEnvironments(renderChart = true) {
    try {
        const res = await fetch('/api/environments');
        const envs = await res.json();
        const container = document.getElementById('env-cards-container');
        if (!container) return;

        container.innerHTML = envs.map(e => `
            <div class="p-4 rounded-xl bg-mongo-card border ${e.has_active_drift ? 'border-amber-500/80 bg-amber-950/20 shadow-lg' : 'border-mongo-border'} space-y-2">
                <div class="flex items-center justify-between">
                    <span class="font-mono text-xs font-bold text-white px-2 py-0.5 rounded ${getEnvBadgeClass(e.env)}">${e.display_name}</span>
                    <span class="text-[10px] font-mono text-slate-400">${e.policy_count} Active Rules</span>
                </div>
                ${e.has_active_drift ? `
                    <div class="p-2 rounded bg-amber-500/10 border border-amber-500/30 text-[10px] text-amber-300 font-semibold flex items-center gap-1">
                        <i data-lucide="alert-circle" class="w-3.5 h-3.5 text-amber-400"></i>
                        <span>Un-attested Drift Detected!</span>
                    </div>
                ` : ''}
                <div class="text-[11px] text-slate-300 space-y-1 pt-1">
                    <div class="flex justify-between"><span>Avg Latency:</span> <strong class="text-white">${e.health.avg_latency_ms} ms</strong></div>
                    <div class="flex justify-between"><span>Success Rate:</span> <strong class="text-emerald-400">${e.health.success_rate_pct}%</strong></div>
                </div>
            </div>
        `).join('');

        lucide.createIcons();
    } catch (e) {
        console.error(e);
    }
}

function initTelemetryChart() {
    const ctx = document.getElementById('telemetryChart');
    if (!ctx) return;
    if (telemetryChart) telemetryChart.destroy();

    const labels = ['-25m', '-20m', '-15m', '-10m', '-5m', 'now'];
    telemetryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'PROD Latency (ms)',
                    data: [8.2, 8.5, 9.1, 8.8, 8.4, 8.2],
                    borderColor: '#00ED64',
                    backgroundColor: 'rgba(0, 237, 100, 0.1)',
                    tension: 0.3,
                    fill: true
                },
                {
                    label: 'PAT Latency (ms)',
                    data: [12.1, 11.8, 12.5, 14.2, 12.0, 11.5],
                    borderColor: '#38bdf8',
                    tension: 0.3
                },
                {
                    label: 'DEV / ENG Latency (ms)',
                    data: [14.0, 15.2, 14.8, 16.1, 15.0, 14.2],
                    borderColor: '#a855f7',
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#94a3b8', font: { size: 11 } } }
            },
            scales: {
                x: { grid: { color: '#1f2e54' }, ticks: { color: '#94a3b8' } },
                y: { grid: { color: '#1f2e54' }, ticks: { color: '#94a3b8' } }
            }
        }
    });
}

// Memory View
async function loadMemory() {
    try {
        const res = await fetch('/api/memory');
        const episodes = await res.json();
        renderMemoryEpisodes(episodes);
    } catch (e) {
        console.error(e);
    }
}

async function executeMemorySearch() {
    const input = document.getElementById('memory-search-input');
    const q = input?.value?.trim();
    if (!q) {
        loadMemory();
        return;
    }
    try {
        const res = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}`);
        const results = await res.json();
        renderMemoryEpisodes(results);
    } catch (e) {
        console.error(e);
    }
}

function renderMemoryEpisodes(episodes) {
    const container = document.getElementById('memory-episodes-container');
    if (!container) return;

    if (episodes.length === 0) {
        container.innerHTML = `<div class="col-span-2 p-8 text-center text-xs text-slate-500">No episodic memory records matched the search query.</div>`;
        return;
    }

    container.innerHTML = episodes.map(ep => `
        <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2.5">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-1.5">
                    <span class="font-mono text-xs font-bold text-indigo-400">${ep.memory_id}</span>
                    <span class="text-[10px] px-1.5 py-0.5 rounded font-mono ${getEnvBadgeClass(ep.environment)}">${ep.environment}</span>
                </div>
                <span class="text-[10px] px-2 py-0.5 rounded font-mono font-bold ${ep.outcome === 'OUTAGE' || ep.outcome === 'ROLLBACK' ? 'bg-rose-950 text-rose-400 border border-rose-800' : 'bg-emerald-950 text-emerald-400 border border-emerald-800'}">${ep.outcome}</span>
            </div>
            <p class="text-xs text-slate-200 font-medium">${ep.summary}</p>
            <div class="text-[11px] text-slate-400">
                <strong class="text-slate-300">Resolution:</strong> ${ep.resolution}
            </div>
            <div class="flex flex-wrap gap-1 pt-1">
                ${ep.tags?.map(t => `<span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">#${t}</span>`).join('') || ''}
            </div>
        </div>
    `).join('');
}

// Attestations View
async function loadAttestations() {
    try {
        const res = await fetch('/api/attestations');
        const attestations = await res.json();
        const tbody = document.getElementById('attestations-table-body');
        if (!tbody) return;

        tbody.innerHTML = attestations.map(a => `
            <tr class="hover:bg-slate-800/40 transition">
                <td class="py-2.5 px-3 font-mono font-bold text-mongo-green">${a.attestation_id}</td>
                <td class="py-2.5 px-3"><span class="px-1.5 py-0.5 rounded font-mono ${getEnvBadgeClass(a.predicate.target_env)}">${a.predicate.target_env}</span></td>
                <td class="py-2.5 px-3 font-mono text-slate-300">${a.predicate.pr_id} <span class="text-slate-500 font-sans">(${a.predicate.pr_author})</span></td>
                <td class="py-2.5 px-3 font-mono text-[11px] text-indigo-300">${a.subject.digest.sha256.substring(0, 16)}...</td>
                <td class="py-2.5 px-3 font-mono font-bold text-emerald-400">${a.predicate.test_status}</td>
                <td class="py-2.5 px-3 font-mono text-[11px] text-slate-500">${a.previous_attestation_hash ? a.previous_attestation_hash.substring(0, 12) + '...' : 'GENESIS'}</td>
                <td class="py-2.5 px-3 text-right flex items-center justify-end gap-1.5">
                    <button onclick="inspectAttestation('${a.attestation_id}')" class="px-2.5 py-1 text-[11px] rounded bg-slate-800 text-slate-300 hover:text-white border border-slate-700">Verify</button>
                    <button onclick="reconstructAudit('${a.attestation_id}')" class="px-2.5 py-1 text-[11px] rounded bg-indigo-950 text-indigo-300 hover:text-white border border-indigo-800">Reconstruct</button>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

async function inspectAttestation(attId) {
    try {
        const res = await fetch(`/api/attestations/${attId}/verify`);
        const result = await res.json();
        const modal = document.getElementById('attestation-modal');
        const content = document.getElementById('attestation-modal-content');
        if (!modal || !content) return;

        content.innerHTML = `
            <div class="p-3 rounded-lg ${result.valid ? 'bg-emerald-950/40 border border-emerald-800 text-emerald-300' : 'bg-rose-950/40 border border-rose-800 text-rose-300'} flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <i data-lucide="${result.valid ? 'shield-check' : 'shield-alert'}" class="w-5 h-5"></i>
                    <span class="font-bold text-xs">${result.signature_status || result.reason}</span>
                </div>
                <span class="text-[10px] font-mono">HMAC-SHA256 verified</span>
            </div>
            <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 overflow-x-auto text-[11px] space-y-2">
                <pre class="text-slate-300">${JSON.stringify(result, null, 2)}</pre>
            </div>
        `;

        modal.classList.remove('hidden');
        lucide.createIcons();
    } catch (e) {
        console.error(e);
    }
}

async function reconstructAudit(identifier) {
    try {
        const res = await fetch(`/api/audit/reconstruct/${identifier}`);
        const result = await res.json();
        const modal = document.getElementById('attestation-modal');
        const content = document.getElementById('attestation-modal-content');
        if (!modal || !content) return;

        content.innerHTML = `
            <div class="p-3 rounded-lg bg-indigo-950/40 border border-indigo-800 text-indigo-300 flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <i data-lucide="file-search" class="w-5 h-5"></i>
                    <span class="font-bold text-xs">Reviewer Reconstruction for ${identifier}</span>
                </div>
                <span class="text-[10px] font-mono">MongoDB Audit Layer</span>
            </div>
            <div class="space-y-3 pt-2 text-slate-300">
                <div class="grid grid-cols-2 gap-2 text-xs">
                    <div class="p-2.5 rounded bg-slate-900 border border-slate-800">
                        <span class="text-slate-500 block text-[10px] uppercase font-bold">1. Identity</span>
                        <div class="font-medium text-white">${result.identity?.initiator}</div>
                        <div class="text-[11px] text-slate-400">Agent: ${result.identity?.agent_builder}</div>
                    </div>
                    <div class="p-2.5 rounded bg-slate-900 border border-slate-800">
                        <span class="text-slate-500 block text-[10px] uppercase font-bold">2. Authority Grant</span>
                        <div class="font-medium text-amber-300">${result.identity?.authority_signoff}</div>
                        <div class="text-[11px] text-slate-400">Pre-Action Check: ${result.pre_action_policy_check?.policy_status}</div>
                    </div>
                </div>

                <div class="p-3 rounded bg-slate-900 border border-slate-800 text-xs space-y-1">
                    <span class="text-slate-500 block text-[10px] uppercase font-bold">3. What Was Executed</span>
                    <div>Target Env: <strong class="text-white">${result.action_executed?.target_environment?.toUpperCase()}</strong> | Status: <strong class="text-emerald-400">${result.action_executed?.status}</strong></div>
                    <div class="text-[11px] text-slate-400">Rules Applied: ${result.action_executed?.policy_changes?.length || 0} rule(s)</div>
                </div>

                <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 max-h-48 overflow-y-auto text-[10px] font-mono">
                    <div class="text-slate-400 mb-1 font-bold">MongoDB Chronological Audit Trail:</div>
                    ${result.chronological_event_log?.map(ev => `
                        <div class="py-1 border-b border-slate-900 flex justify-between">
                            <span class="text-indigo-400">[${ev.event_type}]</span>
                            <span class="text-slate-500">${new Date(ev.timestamp).toLocaleTimeString()}</span>
                        </div>
                    `).join('') || '<div class="text-slate-500">No events logged.</div>'}
                </div>
            </div>
        `;

        modal.classList.remove('hidden');
        lucide.createIcons();
    } catch (e) {
        console.error(e);
    }
}

function closeAttestationModal() {
    document.getElementById('attestation-modal')?.classList.add('hidden');
}

// Drifts View
async function loadDrifts() {
    try {
        const res = await fetch('/api/drifts');
        const drifts = await res.json();
        const container = document.getElementById('drifts-container');
        if (!container) return;

        if (drifts.length === 0) {
            container.innerHTML = `<div class="p-8 text-center text-xs text-slate-500">No un-attested manual changes currently detected. All active network rules have verified cryptographic attestations in MongoDB.</div>`;
            return;
        }

        container.innerHTML = drifts.map(d => `
            <div class="p-4 rounded-xl bg-slate-900 border border-amber-500/40 space-y-2">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <span class="font-mono text-xs font-bold text-amber-400">${d.incident_id}</span>
                        <span class="text-[10px] px-1.5 py-0.5 rounded font-mono ${getEnvBadgeClass(d.env)}">${d.env}</span>
                        <span class="text-[10px] px-2 py-0.5 rounded font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30">${d.drift_type}</span>
                    </div>
                    <span class="text-[10px] font-mono text-slate-400">${new Date(d.created_at).toLocaleTimeString()}</span>
                </div>
                <p class="text-xs text-slate-200">${d.details}</p>
                <div class="p-2.5 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] text-slate-300">
                    Rule: <span class="text-amber-300 font-bold">${d.detected_rule.name}</span> | Port: <span class="text-white">${d.detected_rule.port_range}</span> | Source: <span class="text-indigo-300">${d.detected_rule.source_cidr}</span>
                </div>
            </div>
        `).join('');

        lucide.createIcons();
    } catch (e) {
        console.error(e);
    }
}

async function triggerEmergencyDriftModal() {
    const env = prompt("Enter target environment to simulate emergency drift on (eng/qa/dev/pat/prod):", "prod");
    if (!env) return;

    try {
        const res = await fetch('/api/emergency/drift', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ env: env.toLowerCase(), reason: "Midnight database latency emergency bypass" })
        });
        const data = await res.json();
        alert(`Audit Agent detected out-of-band change!\nDrift incident created and synced to MongoDB Agentic Memory.`);
        switchTab('audit');
    } catch (e) {
        console.error(e);
    }
}

async function reseedData() {
    if (!confirm("Reset database to clean initial hackathon demo state?")) return;
    try {
        await fetch('/api/seed', { method: 'POST' });
        activePRId = null;
        await initSystemStatus();
        await loadPRs();
        await loadEnvironments();
        await loadMemory();
        await loadAttestations();
        await loadDrifts();
        alert("Database successfully reseeded with baseline policies and memory episodes.");
    } catch (e) {
        console.error(e);
    }
}

// Modal Handlers
function openNewPRModal() {
    document.getElementById('new-pr-modal')?.classList.remove('hidden');
}

function closeNewPRModal() {
    document.getElementById('new-pr-modal')?.classList.add('hidden');
}

async function submitCustomPR(e) {
    e.preventDefault();
    const title = document.getElementById('pr-title').value;
    const author = document.getElementById('pr-author').value;
    const branch = document.getElementById('pr-branch').value;
    const port = document.getElementById('pr-port').value;
    const protocol = document.getElementById('pr-protocol').value;
    const action = document.getElementById('pr-action').value;
    const source_cidr = document.getElementById('pr-source-cidr').value;

    const payload = {
        title: title,
        author: author,
        target_branch: branch,
        source_branch: `feature/${author.toLowerCase().replace(/[^a-z0-9]/g, '-')}-change`,
        policy_changes: [{
            name: title,
            port_range: port,
            protocol: protocol,
            source_cidr: source_cidr,
            destination_cidr: "10.1.0.0/16",
            action: action,
            risk_level: port === '22' ? 'CRITICAL' : 'LOW'
        }]
    };

    try {
        const res = await fetch('/api/prs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        closeNewPRModal();
        activePRId = data.pr_id;
        await loadPRs();
        selectPR(data.pr_id);
    } catch (err) {
        console.error(err);
    }
}
