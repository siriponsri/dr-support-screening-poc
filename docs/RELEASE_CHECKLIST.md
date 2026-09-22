# Release Checklist

## Repository
- [ ] final tree intentionally minimal
- [ ] obsolete docs deleted, not archived
- [ ] no `_DRAFT`, milestone handoff, smoke-result, or stale generated files remain
- [ ] README commands/links verified from clean checkout
- [ ] `.env.example` contains no secret
- [ ] license/legal files preserved

## Validation
- [ ] backend tests pass
- [ ] Ruff passes
- [ ] frontend tests pass
- [ ] typecheck passes
- [ ] production build passes
- [ ] root smoke passes where applicable
- [ ] `git diff --check` passes

## Model server
- [ ] clean one-time setup succeeds
- [ ] model revisions/checkpoint hashes verified
- [ ] RETFound smoke inference passes
- [ ] PRISM smoke inference passes
- [ ] healthcheck passes
- [ ] restart passes
- [ ] reboot/systemd recovery passes when used
- [ ] offline restart + inference passes after setup
- [ ] startup does not silently download missing assets

## Clinical workflow
- [ ] PNG/TIFF supported flow passes
- [ ] supported ophthalmic DICOM flow passes
- [ ] unsupported modality state is explicit
- [ ] review app tolerates temporary Model API outage
- [ ] patient/eye resolver unchanged
- [ ] PRISM overlay/confidence behavior matches final UX
- [ ] Dataset/export semantics unchanged
- [ ] optional CVAT path documented/tested to the intended level

## Security/privacy
- [ ] no secrets in repo/logs/screenshots
- [ ] no raw DICOM PHI sent to Model API
- [ ] manual uses only public/synthetic data
- [ ] deployment bind/firewall guidance documented

## Documentation
- [ ] Installation verified
- [ ] Deployment verified
- [ ] Model Server verified
- [ ] Operator Runbook verified
- [ ] Configuration generated from actual settings
- [ ] Backup + restore tested
- [ ] Troubleshooting reflects final release only
- [ ] clinician screenshots regenerated
- [ ] clinician PDF regenerated

## Release
- [ ] final version chosen by owner
- [ ] CHANGELOG updated
- [ ] main clean and synchronized
- [ ] release tag created only after owner acceptance
