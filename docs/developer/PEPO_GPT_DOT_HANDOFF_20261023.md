# HANDOFF: Codex → Pepo GPT Dot — 23 October 2026

สถานะ **READY_FOR_REVIEW / PARTIAL_TECHNICAL_READINESS** ผู้ใช้ขอจัดทำเอกสารส่งต่อให้ Pepo GPT Dot การตอบรับของผู้รับและการโอน writer ownership ยังไม่ได้สังเกต เอกสารนี้เป็น state snapshot ไม่ใช่ normative spec ใหม่ และไม่แทน AGENTS.md, DESIGN.md หรือ current operating guides

## 1. เริ่มอ่านและยืนยันสถานะ

1. อ่าน root AGENTS.md/RTK, README.md, DESIGN.md และ operating guides ที่เกี่ยวข้อง
2. อ่าน [สรุป 27 ปัญหาและร่าง hospital minimum/maximum spec](../planning/HOSPITAL_LOCAL_QA_MIN_MAX_DRAFT_TH_20261023.md) ให้ครบ ตัวเลข hardware เป็นข้อเสนอที่อนุมาน ยังไม่ qualified บนเครื่องโรงพยาบาล
3. เปิด private packet `CLI_TO_PEPO_GPT_DOT_HANDOFF_20261023.md` ในฐาน artifacts เดิมของ owner มี exact local paths, frozen package/ledger hashes และ read order ของ receipts โดยไม่มี credentials
4. ก่อนเขียน ให้ตรวจ repository/worktree/branch/HEAD/status ใหม่ ใช้ bounded branch/worktree และคง single writer ผ่านการประสานงานเดิมของ owner ไม่สร้าง orchestration ใหม่หรือเปิด writer/test/worker หลายตัว

ฐานก่อนเพิ่มเอกสารส่งต่อนี้คือ main `27d386b8d8e1ad573b23b02bae18d3f3dca97587` ซึ่งตรง origin/main; app/runtime control source อยู่ที่ `db3f945c1c8c5fd89bb23ae3e854e2f035fa61af`; application/frontend core ตรงรุ่น qualified `e13db670ba6232ea6e38a14e046f9c607c204244` เอกสารส่งต่อทำให้ HEAD เพิ่มอีก จึงให้ใช้ Git และ `CLI_PEPO_GPT_DOT_HANDOFF_DELIVERY_20261023.json` ใน private artifact root ยืนยัน delivery HEAD แทนการถือ hash ก่อนหน้านี้เป็น HEAD ล่าสุด

## 2. DONE ที่มีหลักฐาน

- C02 รวมใน source ใช้งานจริงและ rebuild frontend บน main แล้ว Local workflow ใช้ภาพจริง UWF/CFP สองภาพกับ **AI จำลอง** → PostgreSQL → export → Chrome แยกจาก actual model inference
- Full backend control-source branch 1,094 PASS / 40 SKIP; main targeted regression 13 PASS; Ruff PASS ส่วน app core ก่อนหน้านั้น 1,081 PASS / 40 SKIP, frontend 284 PASS, typecheck/build/root smoke มี receipts ทั้งหมด เป็นประวัติ qualification ตาม revision ไม่ใช่การ rerun ในงานเอกสารนี้
- Batch เดิม 240 ภาพ / 480 model jobs resolved ครบ: **467 PASS_READBACK** (USPEC184 / RETFound53 / PRISM230), **9 FAILED_NO_RETRY**, **4 BLOCKED_PREMODEL**, **0 NOT_SENT** ไม่มีการ replay terminal jobs
- Durable intents 476 ใหม่ + ประวัติเดิม49 = **525/529** ไม่มี automatic inference retry; ประวัติเดิม49 รวมสถานะเก่าที่เคยส่งไม่ชัดเจนยังคงไว้ ไม่ถือว่า uncertain history นั้นถูกล้างแล้ว
- Actual GPU0 RTX2080Ti เท่านั้น Session เพิ่มที่ owner อนุมัติจบแล้ว 173 PASS / 1 FAILED / 1 PREMODEL จาก175งาน New conservative charge9,800.644s; original4,772.230sคงเดิม; last session cleanupยืนยันครบ
- Fresh PostgreSQL verification 467 ผลตรง response/saved-entry hashes, case-state hash ก่อน/หลังเท่ากัน Export240records,160 byte-preserving UNREVIEWED images,80 admission-skipped,0 physician DR/lesion labels
- HTML gallery240ภาพ/480สถานะ พร้อม per-job provenance/timings/errors และ scientific before/post-filter figures; มี actual representative browser screenshots9ไฟล์ แต่ positive browser→model→DB proof มีเฉพาะ USPEC representative เดิม
- CPU offline post-filter ของ actual PRISM230ภาพ: raw65,639ROI,เสนอซ่อน8raw/3UI, undo7nonempty cases; ไม่มี external pre-mask ไม่มี source/raw ROI overwrite และไม่มี clinical-error-reduction proof
- Hospital sizing DRAFT บันทึก27issue groups: minimum GPU host8cores/RAM32GB/GPU12GB/NVMe1TB; upper QA envelope16cores/RAM64GB/GPU24GB/NVMe2TB **ทั้งคู่ inference concurrency1 และยังไม่ทดสอบ hardware minimum/concurrency**

## 3. BLOCKED / FAIL / NOT_RUN

| สถานะ | รายการ | ขั้นถัดไปที่เล็กที่สุด |
| --- | --- | --- |
| BLOCKED | Main เปิดได้แต่ SERVER_RUNNING / MANUAL_MODE; ordinary three-model connection ไม่ qualified | ตรวจ existing provider configuration/discovery แบบอ่านก่อน แยกจาก finite batch gateway การเรียก inference ใหม่ต้องมี scope/budget ใหม่ |
| BLOCKED | Saved-result viewer ถูกปฏิเสธก่อน process creation ด้วย PTY/CreateProcess access denied | Owner/admin คืน execution path เดิม แล้วเปิด retained results โดยไม่ infer ซ้ำ |
| BLOCKED | CUA ปฏิเสธ HTML file URL | คืน browser access เดิมหรือให้ owner ตรวจด้วยตนเอง ไม่ใช้ HTTP/port/browser/CDP route อื่นเพื่อเลี่ยง denial |
| FAIL | Canonical workspace docs QA มี29 failures ใน owner untracked/ignored archive/presentation/runtime files | เก็บไฟล์เดิม; วางแผน release hygiene กับ owner ไม่ลบ/ย้ายหรือ filter checker เอง Clean tracked-revision QA ผ่านแยกต่างหาก |
| UNKNOWN | TransportError และบาง historical502/503/preparation failures ไม่ได้เก็บ root cause | อ่าน retained diagnostics เพิ่มเท่าที่มี ไม่กล่าวว่ารู้ต้นเหตุหรือซ่อมแล้ว และไม่ยิง terminal job ซ้ำเพื่อเติมหลักฐาน |
| NOT_RUN | Actual hospital install, full offline/restart/restore, multiuser/concurrency/SLA | ทำตาม12 acceptance items ใน sizing DRAFT บน test context ที่อนุมัติ |
| NOT_RUN | Clinical validation, calibration, clinician time saving และ Lightning AI T4 comparison | เป็น qualification แยก ไม่มีผลวัดในชุดนี้ให้อนุมานว่าผ่าน |

กรณีที่แก้แล้วมี evidence I/O/cleanup guard, environment scope, read-only persistence compatibility, line endings, model metadata/checkbox automation, ingress/preparation timeouts เฉพาะ batch, PRISM hook reuse/warmup accounting และ planner8→4→2งานต่อlease ตัวเลข2คือจำนวนงานต่อlease ไม่ใช่ model minibatch size เหตุการณ์เก่าที่ไม่มีรายละเอียดต้องคง UNKNOWN ตาม problem register

## 4. ขอบเขตที่ต้องรักษา

- **ไม่มีงานเดิมเหลือให้ส่ง**: session ที่อนุมัติจบแล้ว ห้าม reset ledger/budget, activate/resumeเพื่อใช้เวลาใหม่ หรือถือ4slotsที่เหลือเป็นสิทธิ์ retry/new jobs คำพูดว่าเพิ่ม budget ได้ไม่ใช่ค่าขยาย requests/time ที่เจาะจง
- Approval เก่ามีเพียง exact-lease owner recovery และ exact175-job new session ที่ใช้ไปแล้ว ไม่ใช่ generic recovery/persistent service grant การยิงโมเดลใหม่หรือ ablation ต้องระบุงาน/count/timeและได้รับอนุมัติต่างหาก
- คง GPU0 restriction; ไม่ใช้ GPU1/V100/Ollama/paid services เพิ่ม ไม่เปลี่ยน weights/parameters/credentials หรือเปิด public/persistent access
- ห้ามข้าม denial, เปลี่ยน ACL/firewall/sandbox/CODEX_HOME เอง ห้ามลบvolume/resetDB/ทับต้นฉบับ ห้ามรวม private artifacts/images/weights/secrets/runtime DB เข้าGit
- Main tracked/index สะอาด แต่มี owner untracked287ไฟล์ที่ hash-preserved จึงไม่อ้างว่า workspace ว่างทั้งหมด ไม่ stash/reset/clean/restoreหรือดูดงานเหล่านั้นเข้าcommit
- รักษา clinician authority, admission/patient-eye semantics, original pixel coordinates, raw/physician separation, reversible suppression และ uncertain retention ไม่สร้าง gold labels อัตโนมัติ
- USPEC เป็น UWF grading, RETFound เป็น CFP grading, PRISM เป็น lesion assistance; PRISM UWF ยัง experimental/NOT_VALIDATED_FOR_UWF ผล QA ไม่ให้ clinical/production authorization และไม่แทน rights review
- B03 เป็น isolated finite QA runtime หลักฐาน API จริงของมันไม่ใช่คำรับรอง ordinary main UI หรือ general hospital deployment

## 5. ลำดับทำต่อสำหรับ Pepo

1. รับช่วงผ่าน owner coordination เดิม ยืนยัน sole writer; อ่าน packet/receipts และตรวจ Git/ledger metadata ก่อน ไม่เปิด model session
2. แยกงานที่ทำได้โดยไม่ยิงโมเดล: อ่านผล467งาน,ตรวจ retained export/figures/unknowns และทบทวน sizing กับ IT ตาม workload/retention จริง
3. จัดการ access blockers ผ่าน owner/admin ในช่องทางเดิม แล้วตรวจ saved-result viewer/HTML พร้อม screenshotsจริง งานนี้ไม่ต้อง replay inference
4. Diagnose ordinary app↔Model API integration ตาม [configuration](../operations/CONFIGURATION.md) และ [Model Server](../operations/MODEL_SERVER.md); มี combined profile ใน source แต่ยังไม่มี current proof ว่า pinned environments ทุกตัวอยู่ร่วมกันได้ใน service เดียว ห้ามเดา endpoint/gateway ใหม่ให้ ready
5. หากต้อง inference บนเครื่องใหม่ ให้เสนอ exact new qualification scope/count/GPU/time budget และ durable ledger ที่อ้างประวัติเดิมก่อน ห้ามนำ480 terminal jobs ไปเริ่มใหม่
6. ถ้าปรับ code ใช้ bounded branch/worktree → focused regression → required branch validation → scoped review → commit/push → integration review → merge/main regression; rebuild frontend/distบนmainเมื่อfrontendเปลี่ยน แยก serial review จาก independent review
7. รายงาน DONE/BLOCKED/NOT_RUN พร้อม actual evidence และ next actor ไม่ประกาศ clinical/production readiness จาก engineering passes

คำสั่งเริ่ม app ที่เคยตรวจ exit0 บน code base เดิมและ scripts ยังตรงกันคือ `.\START_DR_SCREENING.bat -NoBrowser` ผลคือ existing main app / **MANUAL_MODE** ไม่ใช่คำสั่งเปิด model service และไม่ใช่ fresh startup proof บนเครื่องโรงพยาบาล อย่ารัน historical GPU launcher/activation จากเอกสารเก่า

## 6. Private evidence index

ให้ resolve ชื่อเหล่านี้ใต้ฐาน artifacts เดิมของ owner ไม่ได้แนบ private bundle เข้า repository:

| อ่านอะไร | Receipt/path |
| --- | --- |
| ชุดส่งต่อและ delivery HEAD | `CLI_TO_PEPO_GPT_DOT_HANDOFF_20261023.md`, `CLI_PEPO_GPT_DOT_HANDOFF_DELIVERY_20261023.json` |
| สถานะจริง batch/source | `CLI_DEMO_DELIVERY_20261023.json`, `demo-evidence-session04-20261023/FINAL_STATUS.json` |
| Budget/stop/requests | `demo-evidence-session04-20261023/GPU_SESSION_CLOSE.json`, `CLI_APPROVED_SESSION_STOP_OBSERVATION_20261023.json`, original accounting ledger/budgets |
| DB/export/provenance | `demo-evidence-session04-20261023/EXPORT_VERIFICATION.json`, `PER_JOB_EVIDENCE.json/.csv`, `SAVED_RESULTS.json` |
| HTML/manual/ROI | `demo-evidence-session04-20261023/demo.html`, `MANUAL_TH.md`, `PRISM_POSTFILTER_MEASUREMENT.json`, `SUPPRESSION_AUDIT.json` |
| Sizing/hygiene | `CLI_HOSPITAL_QA_SPEC_DELIVERY_20261023.json`, `hospital-qa-spec-draft-20261023/MEASURED_BASELINE.json`, `DRAFT_VERIFICATION.json` และ clean/canonical docs QA logs |
| Causes/fixes/approvals | `CLI_DEMO_OPERATIONAL_LOG_20261022.md`, approval/proposal/repair receipts ที่ packet ระบุ |

อ่าน receipts ตาม snapshot/revision ไม่เขียนทับ output เดิมหรือ rerun one-shot helpers ที่ใช้ exclusive-create/ผูกกับ historical HEAD และอย่าใช้ partial02/recovery03 เป็น current final status
