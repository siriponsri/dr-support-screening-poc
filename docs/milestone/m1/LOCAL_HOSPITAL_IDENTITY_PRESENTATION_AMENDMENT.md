# Owner-approved hospital identity confirmation and presentation amendment

Status: owner approved narrow amendment, 2026-10-16. Applies to the local Windows continuation of M1; does not reopen clinical admission or model contracts.

## Authorized compatibility change

The existing authorized hospital linkage generator produces `HOSPITAL-` plus 24 uppercase hexadecimal characters. An unchanged trusted 33-character key must round-trip through Confirm Image without the 3–32-character manual replacement rule. The exemption requires exact equality between the submitted key, current case identity and authoritative authorized-source admission linkage, including valid hospital provenance and linkage method. Untrusted, modified or newly supplied long keys remain rejected. Strict manual replacement validation remains unchanged. Preserve authorized patient/eye provenance when those values are unchanged; intentional corrections retain existing manual audit semantics.

No patient identifier is shortened, regenerated or rewritten to satisfy validation. No source image, patient/eye grouping, longitudinal matching, clinical decision, annotation or inference lineage is changed by presentation.

## Normal UI

Hospital cases use a short workspace-local label such as Patient 1. Labels are presentation aids, not verified real-world identities, and the UI identifies them as workspace labels. They are allocated uniquely under the existing single-runtime store lock and retained as additive private case JSON metadata, including prior assignments, so reload/restart, case ordering and new images do not renumber existing patients or reuse old labels. No database table/schema migration is introduced. Label metadata does not alter clinical revisions, audit events or annotation hashes. Internal allocation metadata is omitted from case API responses; an additive patient_display_label is returned. Clinical grouping and comparison continue to use the original patient_key, never the display label. Labels are unique within a Workspace, not cross-workspace identifiers.

Normal Worklist, grouping, Confirm Image and Review presentation must not reveal internal hospital keys in visible text, titles, accessibility labels or prefilled correction fields. Explicit patient correction starts with a blank replacement field, explains that the existing link is kept until deliberately changed, permits return to the current link, and permits an explicit unlink action. Opening correction and leaving a replacement blank must keep the existing link; it must not silently unlink. Eye-only edits use the existing resolver KEEP action. Manual replacements use the established pseudonymous identifier rule; generated IDs are not required operator knowledge.

## Acceptance and limits

Regression coverage: exact trusted 33-character preservation; provenance and laterality preservation; tampered/untrusted/invalid manual keys rejected without admission or history changes; valid correction and explicit unlink; stable unique labels after reload/restart and additions, including prior labels; grouping and longitudinal pairing unchanged; IDs absent from normal UI and explicit correction defaults.

Validate affected tests and aggregate backend/frontend/typecheck/build/root/docs checks, private browser views and existing data persistence. No implicit human acceptance of the four FUNDUS_UNCERTAIN images. Owner must still inspect each original and explicitly confirm image/context or leave it blocked. Integration remains subject to AGENTS.md and exact-candidate review.
