# Code and asset provenance

Created under explicit owner authorization in this conversation, September 2026.
The new repository imports no pre-existing OcuForge research code, scientific contracts,
results, dataset configs, or frozen artifacts.

The generic Bridge v1 request/response contracts, gateway, fixture generator, and Online
transport were authored in this session before the standalone override, originally in
local commits e0b6e58 and dc32882. These generic interfaces are carried forward here with
all imports renamed to dr_support and no OcuForge package dependency. The RETFound/PRISM
adapters, asset integrity helper, local store/sync, and sample fetcher were uncommitted
session-authored Bridge work. They are carried forward under the same authorization.
No pre-existing OcuForge contracts or training code is incorporated.

Prior OcuForge commits 2fa5a15, e0b6e58, dc32882 remain unpushed audit history; no reset,
merge, or deletion is performed. Separate audit bundle preserves them.

Third-party model sources are cloned independently into runtime storage, not vendored
as this project's source. RETFound: rmaphoh/RETFound, CC-BY-NC-4.0.
PRISM-DR: zubeyrozeren/PRISM-DR, MIT authored code; Ultralytics AGPL-3.0 dependencies;
release describes weights for academic use. These are research use, not commercial clearance.
HRF images: MedOtter/HRF mirror, CC-BY-4.0 per card; viewer JPEG derivatives.
Synthetic image generator: authored here; not a real patient image.
