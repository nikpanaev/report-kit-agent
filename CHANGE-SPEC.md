# Portable reporting preparation

## Authority, discovery and scope

Owner: repository owner. Decision 2026-10-14: two repositories accepted; prepare local repositories now, later public GitHub distribution; no publication and no changes to existing client agents. Earlier accepted requirements: another employee/device/account, simple questions, future clients only, independently maintained source skills and recurring agent updates.

Product: instruction/plugin package for Codex, not a new app, web UI, report runner or hosted service. MVP: portable setup and future-client/report workflow, approved native-template guard, compatible source skill dependency, offline checks and handover instructions. No existing clients, templates, IDs, chats, exports, credentials or raw histories are product inputs.

Acceptance for this slice: both repositories bootstrap independently; root-relative references; private workspace outside packages; no account preselected; explicit installation permission; separate first pilot and base-template approvals; no inferred messaging or schedules; complete artifact inventory and conservative QA; exact compatible skills identity; offline tests from relocated paths; source/runtime preservation receipt. Another device, live accounts, model behaviour and publication are NOT_RUN.

Open discovery inputs: target OS/Codex surface/account plan, initial client's sources, recipient permissions, distribution license and GitHub URLs. They do not block offline source preparation. Do not invent values.

## Architecture / Engineering decision

Accepted two-repository design is the architecture for this bounded preparation. report-agent owns orchestration, setup, reporting checks and common workflow. report-skills owns reusable source capabilities. Reuse native Codex plugins/skills, connected Google tools and existing capture implementations; Python stdlib checks only. No custom installer, updater daemon, credential bridge or screenshot engine. A local marketplace is a prepared discovery artifact, not an installed plugin.

Public package files are read-only during report work. The employee chooses an external private workspace with clients/<id>/ and runs/<run-id>/. New thread IDs, account links and provider IDs are recorded only there. Relative dependency paths are resolved from the package containing the file, not from cwd. Setup can locate a sibling local package; a future distribution URL must be real and owner-approved.

## Process Profile / responsibility

High Assurance for eventual operation: autonomous tools, credentials, confidential client material and external writes. This slice is offline preparation; no claim of approved High Assurance deployment. Owner owns scope, acceptance/license/distribution decisions. Codex implements and self-checks; independent QA/Security reviewer is unassigned and blocks release. No delegated reviewer is invented.

GUI/Figma: not applicable (no custom GUI). External model API implementation: not applicable (use employee's Codex; no model SDK/key provisioner). Future provider/account data-use terms remain a setup decision. Privacy/identity/external API lifecycle applies to operation, covered by references/workflow.md and references/setup.md; no secrets or real service calls in this slice.

Execution: writes limited to the two new repositories, their task-owned local evidence, and append-only registration in parent PROJECTS-STATUS.md. Existing source repositories and installed skills are read-only. Network only for official documentation/registry metadata when needed; no credentials, Google writes, live captures, costs, installations, remote, push or publication. Local task branch; exact files staged. Unexpected source changes stop scope conclusions.

## Version / maturity / delivery

VERSION is the sole source: 0.1.0-dev.0, prototype/development. plugin.json mirrors it and package check must reject drift. There is no stable release, remote or compatibility promise for another device. Future 1.0.0 requires target-device/account end-to-end check, human acceptance, independent privacy/security and license/packaged release review. Keep private workspace data schema1 separate from package version; update must preserve workspace bytes and pin both package identities. No automatic migration or update from main.

## Risks, recovery and gates

Publication risks: client/secret leakage, unlicensed redistribution, unaudited tool changes, inappropriate access and stale instructions. Mitigations: explicit export inventory, no source Git history, private data outside package, provenance/hashes, pending license gate and separate live-access review. Document controls are not enforced sandbox isolation.

Updates use native plugin/source distribution, explicit approval and exact old/new identities between reports; rollback changes package selection only, never reports/workspace/permissions. Recovery from an uncertain external mutation starts with readback; no blind retries. Temporary files: exact task inventory, receipt/hash before removal; preserve source, accepted artifacts and recovery data. See references/workflow.md.

G0/G1 and bounded architecture/preparation scope derive from direct owner decision; G5S/G5Q/G5P/G6 are pending, not inferred from local tests. No previous product or client gate is reopened or accepted here.
