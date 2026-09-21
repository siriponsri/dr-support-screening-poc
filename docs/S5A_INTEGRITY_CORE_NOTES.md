# S5A Raster Integrity Notes

S5A keeps the existing content-keyed `image_id` contract. When multiple source
references contain identical bytes, they remain one active case for backward
compatibility; the admission record retains every filename and workspace
reference under `integrity.aliases` and marks the case `DUPLICATE_CONTENT`.
The application does not delete, merge, rename, or rewrite any source file.

For a previously observed `WORKSPACE_INPUT/<filename>` reference, a different
source SHA creates a new content-keyed case and marks the new admission record
`SOURCE_CHANGED`. The previous SQLite case and its clinician state remain
durable, but are not copied to the new bytes. A missing prior reference is
recorded as `SOURCE_MISSING` in durable case metadata while remaining out of
the active worklist, preserving S2A1's deleted-file behavior.

Scanning is local and read-only. It computes source facts and admission
quality signals only; it never invokes a model provider.
