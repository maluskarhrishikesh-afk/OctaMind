# OctaMind Security Architecture

Last updated: 2026-03-17

## Goals

This document defines the security architecture that sits on top of OctaMind's workflow engine so we do not lose track of what is being built.

The target is not only a safer assistant, but an architecture that is strong enough for enterprise deployment and structured enough to support a research paper.

## Current Security Baseline

The first shared security slice is now implemented in the runtime:

- `src/agent/security/security_policy.py` provides a centralized inbound security gate.
- `src/agent/security/tool_manifest.py` derives a per-agent runtime tool security manifest.
- `src/agent/hub/processor.py` enforces the inbound gate before routing and tool execution.
- `src/agent/workflows/confirmation_policy.py` already provides approval gates for destructive tools.
- `src/telegram/auto_responder.py` now accepts generic destructive confirmation callbacks as part of the same architecture.

## Security Control Plane

The security architecture should be read as four layers.

### 1. Inbound Request Protection

Entry point: `src/agent/hub/processor.py`

Controls:

- Prompt-injection detection for high-confidence rule override and prompt exfiltration attempts.
- Detection of forged internal context blocks such as `## Session State` pasted by the user.
- Session-scoped abuse throttling with persisted rate-limit state.
- Security audit logging with redaction of obvious secrets and PII patterns.

Current behavior:

- Malicious override attempts are blocked before routing.
- Suspicious meta-prompt references are allowed but audited.
- Excessive request bursts are rate-limited before the router or tools run.
- Operators can inspect these signals in the dashboard via `src/agent/ui/dashboard/security_dashboard.py`.

## 2. Capability Boundary

Entry point: `src/agent/workflows/agent_registry.py`

Controls:

- Agents expose runtime tools only through the shared registry contract.
- Security policy can reason about the same runtime tool map used by deterministic execution.
- `src/agent/security/tool_manifest.py` classifies runtime tools into `low`, `medium`, `high`, and `critical` risk.

This is the boundary where future allowlists, tenant policy, and per-agent tool entitlements should be enforced.

## 3. Execution Safeguards

Entry points:

- `src/agent/workflows/skill_dag_engine.py`
- `src/agent/workflows/skill_react_engine.py`
- `src/agent/workflows/confirmation_policy.py`

Controls:

- Shared destructive-action detection.
- Shared confirmation-required status and stable action keys.
- Channel-specific confirmation UX through payload adapters.

This is the correct place for future step-up authentication, risk-adaptive approval, and policy denial of critical actions.

## 4. Audit, Forensics, and Research Traceability

Runtime files:

- `your_data/runtime_state/security_events.jsonl`
- `your_data/runtime_state/security_rate_limits.json`
- `your_data/runtime_state/destructive_action_pending.json`

Design intent:

- Every security-relevant event should be reconstructable after the fact.
- Logs should preserve enough metadata for analysis without storing raw secrets.
- Security events should be correlatable with workflow and channel events.

Dashboard visibility:

- The security dashboard reads the live runtime files and shows:
	- recent audit events
	- active rate-limit state
	- pending destructive confirmations
	- live runtime tool-risk manifests

## Threat Model

The architecture is primarily designed for these classes of threats:

1. Prompt injection through user input, pasted content, or retrieved documents.
2. Unauthorized destructive actions executed without explicit approval.
3. Abuse through rapid command bursts or automation loops.
4. Accidental leakage of secrets or sensitive identifiers into logs.
5. Cross-channel replay and unsafe callback execution.

## What Is Implemented Now

Implemented now:

1. Shared inbound prompt-injection screening.
2. Shared session-based request throttling.
3. Shared redacted security audit log.
4. Runtime-derived tool security manifest.
5. Generic destructive confirmation buttons working through Telegram callback flow.

Not implemented yet:

1. Per-tool authorization by user, PA, or tenant.
2. Domain allowlists for outbound email, sharing, and posting actions.
3. Data-classification-aware redaction for memories, manifests, and reports.
4. Signed audit records and tamper-evident log chains.
5. Human approval queues and dual control for critical actions.
6. Secret vault integration and credential rotation policy.
7. Retrieval-time document sanitization for prompt-injection-bearing files.

## Enterprise-Grade Roadmap

To make OctaMind enterprise grade, these should be implemented next.

### Identity, Access, and Authorization

1. Per-user and per-PA role model.
2. Agent-level entitlements and per-tool allowlists.
3. Outbound domain policy for email, sharing, posting, and message delivery.
4. Step-up approval for critical actions such as mass delete, external sharing, and bulk mail.

### Data Security

1. Data classification tags for messages, memory, manifests, and tool results.
2. Field-aware redaction before writing memory, logs, and telemetry.
3. Encryption at rest for runtime state files that contain operational metadata.
4. Retention and purge policy for conversation, audit, and context files.

### Runtime Security

1. Per-tool rate limiting instead of only per-session request limits.
2. Policy enforcement based on tool manifest risk level.
3. Sandboxing for browser and file-heavy operations.
4. Safer callback signing or nonce validation for external channel actions.

### Governance and Compliance

1. Tamper-evident audit logs.
2. Security incident timeline reconstruction.
3. Policy versioning so actions can be traced to the active rule set.
4. Admin-facing security review dashboards.

## Research-Paper Worthy Directions

These are the parts that can support a meaningful research paper rather than a product memo.

1. A unified policy architecture for multi-agent LLM systems that separates routing, capability exposure, execution approval, and auditability.
2. Runtime tool security manifests derived from live agent tool maps rather than static YAML definitions.
3. Cross-channel confirmation semantics where the same policy result is rendered as text, buttons, or future approval workflows.
4. Prompt-injection resilience that combines input screening, capability scoping, and action-time approvals instead of relying on prompt wording alone.
5. Evaluation methodology across benign tasks, adversarial prompts, replay attempts, and abuse bursts.

## Proposed Evaluation Suite

The research-grade evaluation set should include at least four buckets.

1. Benign workload: normal email, files, drive, calendar, and browser tasks.
2. Injection workload: prompt override attempts, forged internal context, prompt exfiltration requests.
3. Abuse workload: command storms, repeated destructive confirmations, repeated share/send requests.
4. Safety-critical workload: mass delete, external sharing, high-volume outbound communication.

Metrics to track:

1. Attack detection rate.
2. False positive rate on benign requests.
3. Time-to-decision at the hub boundary.
4. Rate of unsafe tool execution prevented.
5. Audit completeness for post-incident reconstruction.

## Implementation Order

Recommended next sequence:

1. Enforce per-tool policy using the runtime tool security manifest.
2. Add domain allowlists for email, share, and publish flows.
3. Add sensitive-data redaction before memory and context persistence.
4. Add signed or chained security audit records.
5. Add an adversarial evaluation harness on top of the live security dashboard.

## Non-Goals

The current slice does not attempt to solve:

1. Full zero-trust infrastructure.
2. Cryptographic message attestation for Telegram or WhatsApp payloads.
3. Secrets management beyond redaction and audit minimization.

Those belong in later phases after policy enforcement and observability are stable.