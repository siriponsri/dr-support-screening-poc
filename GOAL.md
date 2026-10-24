# GOAL — Hospital M1 สำหรับแพทย์ทดลองใช้และจัดทำข้อมูลกำกับ

เอกสารภาษาไทย ฉบับ 1.3 · 23 ตุลาคม 2569 (2026-10-23) · 1.1 ตรวจซ้ำแบบอ่านอย่างเดียว; 1.2 บันทึกการกลับมาทำงานต่อและความคืบหน้า; 1.3 ผล QA_SERVER live session ดู §19.1

> **อัปเดต 1.6 (24 ต.ค. 2569):** UX ระยะ A merge main `e52863d` (ซ่อนข้อมูลเทคนิค, PRISM quality gate, ปุ่มเกรด, Confirm Image มีภาพ+คุณภาพ, Finish บอกจำนวน AI, Worklist quick filter/quick look); sidebar ย่อ/ขยาย/ซ่อนและภาพใหญ่ขึ้น `ca5e3bd`; แก้ AI READY ค้าง `061193a`; หลักฐาน local TEST_ONLY: AC-07 PASS, AC-08 PASS (app restart), AC-12 PARTIAL, AC-10 NOT_RUN พร้อม blocker; แก้ admission timestamp ไม่ให้ถูกเขียนใหม่ทุก start (`75d41f9`) และ rescan ไม่ล้างผู้ยืนยันภาพ (`9cde657`) แล้ว (owner อนุมัติทั้งสองเรื่อง)

> **อัปเดต 1.3:** QA_SERVER GPU session ปิดแล้ว (window ปิดถาวร): USPEC และ RETFound ผ่าน ordinary UI → actual model → PostgreSQL readback ครบ fresh/restart/recovery รวม 6 requests (ledger 525 → 531); **PRISM ส่งไม่ได้เลย (0 requests)** เพราะ preview gate ต้องการ recorded source attestation ที่ admission ปกติไม่บันทึก — เป็น STOP item รอ owner ตัดสินใจ ดู HANDOFF §25

> **อัปเดต 1.2:** owner สั่งให้กลับมาทำงานต่อในแชตแล้ว โดย **Claude Code เป็นผู้เขียนโค้ดแอปเพียงรายเดียวในรอบนี้** (VS Code Codex ห้ามเขียนพร้อมกัน) รายละเอียดการอนุมัติ, งานที่ทำแล้ว และงานที่ติดอยู่ ดู HANDOFF §23 ข้อความ "PAUSED" และ "Codex เป็น sole writer" ด้านล่างเป็นสถานะ ณ ฉบับ 1.0/1.1

**เป้าหมาย:** ส่งมอบ Hospital M1 ที่ติดตั้งและดูแลได้จริง ใช้ให้แพทย์ทดลอง workflow และทำ data labeling ภายใต้การกำกับของแพทย์ ด้วย application เดียวและ deployment profiles สองแบบ คือ **QA Server** และ **QA Local**

**สถานะ ณ การอ่านหลักฐาน:** `M1_NOT_COMPLETE / ENGINEERING_PAUSED_BY_OWNER` งานเอกสารนี้ได้รับอนุญาตแยกต่างหาก การมี GOAL.md ไม่ใช่คำสั่งให้เริ่ม implementation, tests, GPU session, migration หรือบริการต่อเอง ผู้เขียน application code ยังคงเป็น VS Code Codex ของผู้ใช้เพียงรายเดียว

## 1. จุดตรวจและวิธีอ่านเอกสารนี้

| รายการ | Snapshot ที่ตรวจได้ |
| --- | --- |
| Repository | `C:\Users\User\Desktop\myProject\dr-support-screening-poc` |
| เวลาตรวจ Git และเอกสารฐาน | `2026-10-23T10:33:02Z` ใช้ UTC เพื่อเทียบ receipts; เท่ากับ 17:33 น. Asia/Bangkok |
| Branch / HEAD | `main` / `49ad62fdef2ddc133b1e9f14f06aa24a2d2199af` |
| Implementation base ตาม HANDOFF | `7be279deb422c1fb1d50e076f58d008b293e733a`; HEAD ปัจจุบันเป็น documentation successor |
| Tracked/index state ก่อนเพิ่ม GOAL | ไม่มี tracked/index changes จาก `git status --porcelain=v1`; มี owner untracked เดิม จึงไม่เรียกว่า workspace ว่างทั้งหมด |
| Owner untracked ที่ต้องรักษา | `.vscode/`, `DR_M1_LOCAL_CODEX_HANDOFF.md`, `docs/benchmarks/`, `docs/deployment-preparation/`, เอกสาร Claude handoff/review สามไฟล์ และ `docs/presentation/dr-screening-demo/` |
| GOAL.md เดิม | ไม่พบในการตรวจช่วงต้นและ checkpoint ข้างต้น ต้องตรวจซ้ำก่อนสร้างและห้ามทับไฟล์ที่ผู้อื่นสร้างระหว่างทาง |
| HANDOFF ที่ใช้ | [HANDOFF.md](HANDOFF.md), checkpoint ประมาณ 10:10 UTC; file SHA-256 ตอน GOAL 1.0 `7214155e8b7267fe16925f737685cec8c62ae4e3baa7a7d876cdf8da5e66ca8f`; หลังเพิ่ม §22 (addendum ตรวจซ้ำ 10:53 UTC) `d01e6fa947ad64af574e87688d2c2c9440c54e58d963abc7b8994efdbdf2a37f` ยังไม่ commit |
| ตรวจซ้ำล่าสุด (GOAL 1.1) | `2026-10-23T10:53:22Z`: main/`origin/main` (ls-remote) ยังเป็น `49ad62f`, ไม่มี tracked changes, candidate heads ทุกตัวเท่าเดิมและยังไม่อยู่ใน main, listener 8000/54805 PID เดิม รายละเอียดใน HANDOFF §22 |
| Integration (1.2) | owner อนุญาตแล้ว: **main = `4ddb6a3` push แล้ว**; full suite ก่อน merge และ main regression หลัง merge 1855 PASS / 67 SKIP ทั้งคู่ |
| MS-03/04 (1.2) | **อยู่ใน main `a99cd68`** (full 1925 PASS / 67 SKIP); deploy `m1-session-20261023-s02` + CPU identity ผ่าน; **owner อนุมัติ proposal v2 `5a06f23c…` แล้ว** APPROVAL `fc1f32ed…`; workspace TEST_ONLY `ws_m1_63ed86c7…` สร้างแล้ว ภาพ acceptance 6 ภาพผ่าน Confirm Image; ยังไม่เปิด window/lease/GPU รอ owner สั่งเริ่ม (ดู HANDOFF §24) |
| QA_SERVER session (1.3) | **ปิดแล้ว** `COMPLETE.json` cleanup/window_stop/ledger_close CONFIRMED; global grading 6/6 PASS_READBACK; PRISM 0/3 ส่งไม่ได้ (preview attestation gap); post-fix ไม่รัน; launcher fixes 5 commits merge เข้า **main `d7ca474`** push แล้ว (full 1926 PASS / 67 SKIP) ดู HANDOFF §25 |
| ไฟล์ untracked ใหม่หลัง checkpoint | `GOAL.md` (ไฟล์นี้) และ `CLAUDE.md` (คำแนะนำสำหรับ Claude Code ชี้ให้อ่าน HANDOFF/GOAL ก่อน) ยังไม่ commit |
| Combined candidate | Local branch ref `feat/m1-native-accounting` = `8329c31dfbe973b6819479f435e0c146906e85e6`; เป็น candidate แยกจาก main ตาม HANDOFF |
| Remote-provider candidate | Local branch ref `feat/m1-workspace-remote` = `6c0de66478f6f37d504c52a98c48f9c13787a978`; final delta review ยัง pending ตาม HANDOFF |

เอกสารนี้แยก **สิ่งที่ต้องได้**, **ข้อเท็จจริงที่มีหลักฐาน**, **สิ่งที่ยังไม่ทำ** และ **สิทธิ์ที่ต้องได้รับก่อนดำเนินการ** ออกจากกัน ตัวเลขผลทดสอบและการเปิดบริการทุกค่าด้านล่างเป็นผลเดิมตาม revision/receipt ที่ระบุ งานเขียน GOAL นี้ไม่ได้รัน tests, SQL, inference, SSH, containers หรือบริการใหม่

### 1.1 ลำดับอำนาจและหลักฐาน

1. เจตนาล่าสุดของ owner กำหนด Hospital M1 และสอง QA profiles ไม่ลดกลับเป็น demo-only
2. [AGENTS.md](AGENTS.md), [DESIGN.md](DESIGN.md) และ frozen clinical/admission/model/coordinate/provenance contracts ยังคงใช้ การเปลี่ยนที่กระทบสัญญาเหล่านี้ต้องระบุ conflict และขอการตัดสินใจที่ตรงประเด็น
3. [Hospital M1 release candidate spec](docs/milestone/m1/HOSPITAL_M1_RELEASE_CANDIDATE_SPEC.md) เป็น acceptance contract ปัจจุบัน อ่านร่วมกับ [mutable PRISM authority](docs/milestone/m1/M1_MUTABLE_PRISM_ENTRY_AUTHORITY.md) และ [ข้อเสนอ GPU ที่อนุมัติแล้ว](docs/planning/HOSPITAL_M1_GPU_REQUEST_PROPOSAL_20261023.md)
4. HANDOFF เป็น checkpoint ของ implementation และสิทธิ์ที่รายงานไว้ ไม่ใช่ผลรับระบบแทน receipts
5. คู่มือปฏิบัติการใช้บอกวิธีตาม release ที่ตรงกัน ส่วนแผน, proposal, checklist และ acceptance matrix ที่ยังไม่ execute ใช้เป็น **requirements ไม่ใช่ implementation evidence**

ข้อความใน AGENTS ที่ว่าไม่มี HANDOFF แยก เป็นบริบทก่อน owner สั่งสร้าง HANDOFF.md ใหม่ ไม่ใช่เหตุให้ละเลยไฟล์ล่าสุด ข้อความเก่าใน master plan ว่า Phase 1–4 ได้รับ owner acceptance ให้รักษาไว้ตามขอบเขตเดิม ไม่แปลว่า Hospital M1 deployment หรือ Phase 5 ผ่านแล้ว

### 1.2 ขอบเขตการตรวจรอบนี้

อ่านเอกสารหลัก, operating guides และ retained receipts ที่เกี่ยวข้อง แล้วตรวจ source เฉพาะจุดเพื่อยืนยันช่องว่าง ordinary app binding, deployment-profile validation และ recovery guard ไม่ได้ตรวจ codebase ใหม่ทั้งหมด ไม่อ่าน secret values หรือ private `.env`

Git ปฏิเสธการอ่าน status/diff ของ `m1-app-workspace-runtime-worktree` ด้วย `detected dubious ownership` ระหว่างบัญชี owner กับ sandbox จึงไม่เปลี่ยน `safe.directory` และไม่อ้างว่าได้ยืนยัน Git state ปัจจุบันของ worktree นั้น ตัวเลข WIP 92 additions / 3 deletions เป็น **HANDOFF-reported** การอ่าน source ที่ได้รับอนุญาตแยกต่างหากพบ preview construction ที่ยังไม่ผูก workspace authority สอดคล้องกับรายงาน

**อัปเดต 1.1:** การตรวจซ้ำเวลา 10:53 UTC อ่าน `git status` ของ worktree นั้นได้โดยไม่ถูกปฏิเสธ ยืนยันว่ายังอยู่ที่ `1dfdeba` และแก้เพียง `dr_support/api/_factory.py` แบบ unstaged +92/−3 ตรงกับ HANDOFF ไม่ได้อ่านหรือแก้เนื้อหา diff

โมดูล `Get-Acl` โหลดไม่ได้ จึงไม่ได้ยืนยัน ACL ใหม่ในรอบนี้ Metadata พบ dedicated private directory และไฟล์ที่ระบุอยู่ แต่การมีไฟล์ไม่ใช่ privacy-check PASS ปัจจุบัน ดูขอบเขตหลักฐาน credentials ในหัวข้อ 11

## 2. ความสำเร็จที่ผู้ใช้ต้องได้รับ

เมื่อส่งมอบ M1 แพทย์และผู้ดูแลต้องใช้ release ที่ระบุรุ่นเดียวกันได้ตั้งแต่ติดตั้ง เปิดระบบ เลือกภาพ UWF/CFP ขอ AI ที่ตรง modality ตรวจผลและแก้ grade/lesion ROIs บันทึก เปิดกลับมาแก้ และส่งออกข้อมูลพร้อมภาพจัดตาม grade ได้ โดยไม่ต้องให้ผู้พัฒนาเปิด terminal คอยประคองแต่ละภาพ

คุณค่าหลักคือข้อมูลกำกับที่ตรวจย้อนกลับได้และ workflow ที่ใช้ทดลองกับผู้ใช้จริง การลดภาระแพทย์ต้องวัดจากงาน review จริง ไม่สรุปจากจำนวน ROI ที่ลดลงหรือจำนวน tests ที่ผ่าน ความพร้อมเชิงปฏิบัติการต้องพิสูจน์ด้วย release และ target ที่ใช้งานจริง

คำว่า “production สำหรับ deploy โรงพยาบาล” ใน milestone นี้หมายถึงความพร้อมติดตั้ง ดูแล กู้คืน และควบคุมข้อมูลสำหรับ **supervised evaluation/annotation** ตามสิทธิ์ที่ได้รับ ไม่ใช่การรับรอง autonomous diagnosis, autonomous referral, ความแม่นยำทางคลินิก หรือสถานะเครื่องมือแพทย์

### 2.1 อยู่ใน M1

- Application เดิม, mixed UWF/CFP workflow และ PostgreSQL พร้อมสอง deployment profiles
- No-code install/start/status/stop, database readiness, restart/reboot recovery และ model services ที่ให้บริการต่อเนื่องตลอดช่วงผู้ใช้ที่ตกลงไว้
- Actual modality-appropriate inference, physician review/edit, persistence, reopen, provenance และ training export รวม grading-organized image folders ภายใต้ source/export policy
- Mask/input visibility และวิธีลด peripheral/non-retinal PRISM ROIs ที่ย้อนคืนได้ พร้อมการประเมิน lesion loss
- Versioned package, secret-free profile templates, คู่มือดูแล/backup/restore/rollback, E2E evidence, mask gallery, HTML team presentation และ manual deployment walkthrough

### 2.2 อยู่นอกขอบเขตหรือเป็นงานแยก

- การสร้าง screening/referral rules ใหม่, DME diagnosis, autonomous decision หรือ clinical accuracy claims
- การเปลี่ยน ontology, reviewed-negative rubric, patient/eye/visit semantics หรือ model/checkpoint/thresholds เพื่อให้ acceptance ผ่าน
- การ train/fine-tune, online learning หรือยกระดับ pseudo-label เป็น gold อัตโนมัติ; การ fine-tune UWF ในอนาคตต้องใช้อีก versioned dataset และการอนุญาตแยก
- PACS/OCT/MRI/DICOMweb, two-way DB synchronization, SSO/ระบบบัญชีองค์กร หรือ multiuser scaling ใหม่ที่ยังไม่ตกลง
- การย้ายไป paid cloud, ใช้ GPU อื่น, เปลี่ยน ACL/firewall/credentials/services หรือเปิด public access โดยอาศัย GOAL นี้เป็นสิทธิ์

อย่าใช้ non-goals เหล่านี้เพื่อตัดงาน M1 ที่ตกลงแล้ว เช่น mask, persistent service, PostgreSQL หรือ backup/restore ออกไปโดยปริยาย

## 3. สถาปัตยกรรมสอง QA profiles

ใช้ codebase และ clinical/data contracts เดียวกัน แยกด้วย `DR_SUPPORT_DEPLOYMENT_PROFILE=QA_SERVER` หรือ `QA_LOCAL` ตัวเลือกนี้แยกจาก `APP_PROFILE` และ `MODEL_RUNTIME`

| ประเด็น | QA Server (`QA_SERVER`) | QA Local (`QA_LOCAL`) |
| --- | --- | --- |
| Review app/UI/API | Hospital/workstation ตาม target ที่อนุมัติ; browser และ app เป็น workflow เดิม | อยู่บน hospital hardware ตาม topology ที่เลือก |
| PostgreSQL / workspace / annotations | ที่เก็บของ hospital/workstation หรือ DB service ที่ IT อนุมัติ | อยู่ใน hospital boundary; ไม่ต้องพึ่ง DB ภายนอกระหว่าง offline operation |
| Originals, derivatives, exports | Approved local/hospital storage; ไม่ย้ายเป็น authoritative records บน team Model API | อยู่บน hospital hardware/storage ทั้งหมด |
| Models/weights/inference | Team `dr-train` ผ่าน private Tailscale route ที่อนุมัติจริง | อยู่บน hospital hardware พร้อม offline assets ครบ |
| App runtime | `APP_PROFILE=review`, `MODEL_RUNTIME=remote` | ค่า app เช่นเดียวกัน; `remote` หมายถึง HTTP Model API อีก process ซึ่งอาจเป็น loopback |
| Model endpoint | Verified private endpoint หรือ owned authenticated loopback tunnel ตาม bind จริง | Loopback หรือ Compose service `gateway` ตามสัญญาปัจจุบัน; image name `model-gateway` ไม่ใช่ service DNS |
| External connectivity | ต้องมี route/auth/data-transfer approval และ backend connectivity จริง | Normal operation ไม่ต้อง internet/dr-train/cloud; ไม่ fallback ออกนอก site เงียบ ๆ |
| หลักฐานรับระบบ | Workstation → team API และ target hospital route ต้องแยกกัน | ต้องระบุเครื่องจริง; การรันบนอีก host ไม่ใช่ hospital-target PASS |

Model API ไม่ใช่ authoritative clinical-record store ต้องคงหลักการ stateless ของข้อมูล review แม้ runtime จะมี private accounting/operational receipts ข้อมูลชั่วคราวและ retention ต้องอยู่ในขอบเขตที่อนุมัติ

### 3.1 Network และ data boundary

- Closed hospital VLAN ไม่ถือว่าเข้าถึง Tailscale หรือ dr-train ได้ ก่อน QA Server ต้องให้ IT ยืนยัน route, outbound policy, host/authentication, endpoint ownership และการส่ง image payload ที่ data owner อนุญาต
- ถ้า remote API bind loopback ต้องมี tunnel mapping ที่ตรวจทั้งสองฝั่งแล้ว Remote `127.0.0.1` ไม่ใช่ Windows loopback โดยอัตโนมัติ และเลข port ใน HANDOFF เป็นประวัติ ไม่ใช่ launch recipe ปัจจุบัน
- หาก site ไม่อนุญาต external route ให้ใช้ QA Local และเตรียม offline inventory ไม่แก้ network หรือเปลี่ยนทางเพื่อหลบข้อห้าม
- ส่งเฉพาะ bytes/contract identifiers ที่จำเป็นตาม Bridge ปัจจุบัน ไม่ส่ง local paths, resolver/OCR/patient fields หรือ raw DICOM headers เป็น payload เพิ่มเอง ภาพยังอาจเป็นข้อมูลอ่อนไหว จึงต้องมี data-transfer authorization แม้ metadata ถูกลดแล้ว
- `QA_LOCAL` ต้องปฏิเสธ external endpoint, redirects และ manual endpoint replacement ที่ขัดกับ configured identity การผ่าน pure endpoint validator ยังไม่พิสูจน์ว่าไม่มี external dependency ใน runtime
- การเปิด remote Review บน Lightning เป็น workflow ที่ queue/DB อยู่บน Lightning ไม่ใช่ QA Server แบบ app/PG/images อยู่โรงพยาบาล และไม่ใช้เป็นหลักฐานอ่าน Windows roots สำเร็จ

### 3.2 สิ่งที่ต้องระบุในแต่ละ installation

Release/commit, served frontend build, OS/driver/GPU, provider environment inventory, DB/version/schema/workspace, storage roots และสิทธิ์, model/checkpoint/preprocessing pins, selected mask stage/version, private endpoint binding, operational owner และ backup destination ต้องระบุแบบไม่เปิด secret

ไม่กำหนด topology หรือ hardware ใหม่จากชื่อ “local” เพียงอย่างเดียว ให้ใช้ [deployment architecture เดิม](deployment/dual-mode/README.md) และยืนยัน target จริง ระบบ localhost single-user เดิมและ model bearer token ไม่ใช่หลักฐานว่ามี browser application login หรือ multiuser authorization แล้ว

## 4. Workflow ที่ต้องใช้งานได้

```text
เปิดระบบและตรวจ profile/DB/model readiness
→ เลือก workspace และนำเข้า UWF/CFP จาก approved roots
→ ยืนยัน image context ตามสัญญาเดิม
→ ขอ actual AI ที่รองรับ modality
→ เห็น Original + effective input/mask + AI evidence อย่างถูกต้อง
→ แพทย์ตรวจ/แก้ grade และ lesion ROIs พร้อม provenance
→ บันทึก PostgreSQL
→ ปิด/เริ่มใหม่และ reopen/edit
→ export dataset + physician-confirmed grading folders
→ ใช้ snapshot ที่ตรวจย้อนกลับได้สำหรับงานที่อนุญาต
```

เมื่อ AI ไม่พร้อม manual review ต้องใช้ต่อได้อย่างซื่อตรง แต่ manual mode ไม่ทำให้ actual-inference acceptance ของ Hospital M1 ผ่าน

### 4.1 ข้อกำหนด workflow ที่มีรหัสคงที่

| ID | ข้อกำหนด | เงื่อนไขตรวจรับ |
| --- | --- | --- |
| WF-01 | ใช้ mixed UWF/CFP queue และ workspace เดิม ไม่สร้างแอปแยกตาม modality | ยืนยัน modality/origin แยกกัน, context ที่ไม่ทราบยังไม่ถูกเดา และเลือก workspace ชัดเจน |
| WF-02 | รักษา image admission, patient/eye/visit และสาม human-confirmation milestones | Confirm Image, Confirm DR Grade, Finish image & next มีความหมายเดิม; filename/order ไม่สร้าง clinical chronology |
| WF-03 | Route UWF grading ไป USPEC, CFP grading ไป RETFound และ lesion assistance ไป PRISM ตาม capability ที่ผ่าน scope | มี real request/result/pins ของแต่ละ capability; PRISM ไม่เป็น DR grader และ UWF ยัง experimental |
| WF-04 | แสดง Original, actual effective input/mask และขั้นที่ใช้จริง | ผูก image/mask/analysis hash กับ invocation เดียวกัน; post-filter ห้ามเรียกว่า model-input pre-mask |
| WF-05 | แพทย์แก้/ปฏิเสธ/เพิ่ม grade และ ROIs ได้ใน original-image coordinates | Raw AI ไม่เปลี่ยนตามการลาก human correction; score ของ AI เดิมไม่กลายเป็น score ของ corrected annotation |
| WF-06 | จบ case ได้โดยไม่ต้อง confirm AI ROI ทุกชิ้น และไม่เพิ่ม mandatory mask approval รายภาพ | Core review/completeness ชัด; protected PRISM prepare/ack/entry protocol ยังรักษาตามสัญญา ดู MK-06 |
| WF-07 | Save, SQL readback, reopen และแก้รอบถัดไปตรงกัน | เทียบ revision, grade, geometry, reviewer/time, source/model/mask lineage และ invalidated confirmation เมื่อมีการแก้ |
| WF-08 | แยก DR-ready กับ Lesion-ready | Grade confirmation ไม่ยืนยัน lesion; reviewed-empty ไม่เป็น gold-negative; untouched AI ไม่เป็น human label |
| WF-09 | Export dataset และ grading folders จาก snapshot ที่ระบุชัด | DB/API/UI/export สอดคล้องกัน, originals byte-preserving, grouping ใช้ physician-confirmed grade เท่านั้น และ export ที่ไม่มีสิทธิ์ยังต้องปฏิเสธ |
| WF-10 | Model unavailable/error/unsupported ไม่กลายเป็นผลปกติ | ไม่มี grade 0 หรือ empty findings ปลอม; แสดงเหตุผลที่ผู้ใช้เข้าใจและคง unsaved/manual work |
| WF-11 | เคารพ DESIGN และ clinical viewer ที่ freeze | ภาพเป็นส่วนหลัก, keyboard/focus ใช้ได้, AI/human แยกด้วยข้อความ/รูปแบบนอกเหนือจากสี และ geometry ไม่เปลี่ยนเมื่อ zoom/fullscreen |

Grade 0–4, Ungradable และ deliberate second review ใช้ความหมายตาม accepted contracts ไม่เพิ่ม DME/referral หรือแก้ taxonomy เพื่อปิดงาน UI การรับรอง case-level annotations ไม่ได้ยืนยัน AI ROIs ทุกชิ้น

## 5. Mask และการลด peripheral PRISM ROIs เป็นงาน M1

เป้าหมายคือช่วยลด ROI ผิดบริเวณ UWF rubber/non-retinal edges และลดงาน cleanup ของแพทย์ พร้อมคงบริเวณจอประสาทตาที่ไม่แน่ชัดและกู้ ROI ที่ถูก suppress ได้ การซ่อนน้อยลงหรือมากขึ้นเพียงอย่างเดียวตัดสินคุณภาพไม่ได้

| ID | ข้อกำหนด | หลักฐานที่ต้องมี |
| --- | --- | --- |
| MK-01 | ระบุ stage ของวิธีที่เลือก: input pre-mask, inference tiling/ROI handling หรือ output post-filter | แผนภาพ/คำอธิบายตรง implementation, method/parameter version และ actual input/output hashes |
| MK-02 | เก็บ originals และ raw detections ครบ | Raw ROI IDs/geometry/scores คงเดิม, suppression มีเหตุผล/lineage, restore/undo คืนได้หลัง save/reopen |
| MK-03 | บริเวณ uncertain ต้องตรวจกลับได้ | ไม่ตัด uncertain retina ทิ้งอัตโนมัติ; retain-all/fallback และการแสดง warning ตาม policy |
| MK-04 | เปรียบเทียบ baseline กับวิธีที่เลือกบน actual PRISM outputs | Gallery แสดง original, effective mask/input, raw ROIs, hidden/retained/uncertain และ restored state ของ case เดียวกัน |
| MK-05 | ประเมิน false-ROI suppression และ potential true-lesion loss คู่กัน | Human adjudication/rubric และ denominators; บันทึก disagreement/unknown ไม่สมมติ clinical benefit จาก suppression count |
| MK-06 | Workflow ไม่สร้าง mask-confirmation task ใหม่ทุกภาพ | แยก usability goal ออกจาก existing protected preview acknowledgment; ห้ามเรียก raw route เพื่อข้าม rejection หากต้องเปลี่ยน frozen interaction ให้เสนอ amendment ที่เจาะจงก่อน |
| MK-07 | เลือกหรือผสมวิธีตามหลักฐานได้ | บันทึก composition/stage/version; label-assist profile อาจใช้ masking แรงกว่า future fine-tuned UWF production profile แต่ไม่เปลี่ยน weights/thresholds โดยพลการ |

หลักฐานปัจจุบันคือ **generic CPU preview/reversible output post-filter** บน retained PRISM 230 cases มี 65,639 raw ROIs, proposed hidden 8 raw / 3 UI และ historical undo exercise 7 nonempty cases วิธีนี้ **ไม่ได้เปลี่ยน model input** และ clinical error reduction เป็น `NOT_MEASURED` เก็บตัวเลขแต่ละ state แยกกัน ไม่ใช้ 8 เป็นจำนวน false positives ที่แพทย์ยืนยันแล้ว

เริ่มเปรียบเทียบจาก retained outputs โดยใช้ **0 new inference requests** ตาม scope ที่อนุมัติ หากต้องทดสอบ external input pre-mask ใหม่ ให้เสนอ exact requests/time และ identities ก่อน ไม่ถือว่าใช้สิทธิ์ zero-request comparison ได้

## 6. ข้อมูล, PostgreSQL และการส่งออก

| ID | ข้อกำหนด | เงื่อนไขตรวจรับ |
| --- | --- | --- |
| DT-01 | PostgreSQL เป็น authoritative review store ของ Hospital M1 | Readiness ตรวจ actual configured DB และ `SELECT 1`; ไม่มี silent SQLite fallback หรือเปลี่ยน DB เอง |
| DT-02 | Migration กับ runtime privileges แยกกัน | ตรวจ migration checksums/compatibility; runtime ใช้ least privilege และ startup mode `verify`; ไม่ใช้ administrator เป็น final app identity |
| DT-03 | แยก raw AI, physician annotations, reviewed/adjudicated gold และ pseudo-labels | Provenance/reviewer/revision/source ชัด; ไม่มี auto-promotion เพราะแสดงผล, save หรือ case-level confirm |
| DT-04 | Originals และ coordinate lineage ไม่เปลี่ยน | Hash ก่อน/หลังตรง, original pixel coordinates กับ derivative transforms ย้อนกลับได้ และไม่ rename/recompress เพื่อแก้ upload |
| DT-05 | Auditability ตลอด lifecycle | Image/analysis/mask/request/result hashes, model/bundle/checkpoint/preprocessing versions, parameters, reviewer/time, annotation revision และ policy/taxonomy versions ตรวจย้อนกลับได้ |
| DT-06 | Test/real physician data แยกกัน | TEST_ONLY workspace/reviewer/labels, fixtures และ engineering recovery grades ไม่ปน physician training export หรือถูกเรียก clinical gold |
| DT-07 | Export eligibility ใช้ frozen task-specific policy | Raw/unreviewed/rejected AI ไม่เข้า human labels; reviewed-none ไม่สร้าง negative label เอง; patient grouping ไม่สร้าง auto train/test split |
| DT-08 | Snapshot และ image folders ตรวจทานกับ SQL ได้ | ระบุ data revision/snapshot แยกจาก code commit; copies byte-identical, unknown/unreviewed/excluded และ skipped reasons ชัด |

ดู [dataset manifest](docs/reference/DATASET_MANIFEST.md) และ accepted Phase 4 contracts ประกอบ โครงสร้าง export ต่าง generation ต้องระบุ schema/policy ของมันเอง ไม่เอาชื่อไฟล์/field จาก manifest เก่าไปอ้างว่าตรงกับ training snapshot ใหม่โดยไม่ได้ตรวจ

**อัปเดต 1.2 (owner อนุมัติในแชต 23 ต.ค.):** อนุญาตให้ export ระเบียน `HOSPITAL_AUTHORIZED` ในเครื่องตามการตรวจ identity ที่มีอยู่แล้วใน `services/dataset.py` (ไม่ต้องแก้โค้ด) โดยยังต้องแยก physician/TEST_ONLY และใช้กฎ eligibility เดิม ข้อความเดิมด้านล่างเป็นสถานะก่อนการอนุมัตินี้

**Hospital-origin export ยังไม่ถือว่าอนุญาตจาก GOAL นี้** เป้าหมาย M1 ต้องปิดเส้นทางส่งออกที่เหมาะกับ physician dataset พร้อมสิทธิ์และหลักฐาน แต่ frozen denial ปัจจุบันต้องคงอยู่จนมี approved origin/permission/export contract ที่ตรงขอบเขต การจัด folders ไม่ได้พิสูจน์ reviewer identity หรือ training readiness

## 7. Service lifecycle และความพร้อมปฏิบัติการ

| ID | ข้อกำหนด | เงื่อนไขตรวจรับ |
| --- | --- | --- |
| OP-01 | ต่อยอด canonical no-code entrypoints เดิม | `FIRST_RUN.bat`, `START_DR_SCREENING.bat`, `CHECK_SYSTEM.bat`, `STOP_DR_SCREENING.bat` พร้อม model-host procedures ตาม target; ไม่สร้าง START variants หลายชุด |
| OP-02 | Start ดูแล DB ตาม ownership และรอพร้อมจริง | Owned runtime เริ่มหรือให้คำแนะนำที่ทำได้จริง; external DB ตรวจตาม configuration; ไม่ให้ผู้ใช้รัน npm/pip/migrations ทุกวัน |
| OP-03 | Status แยกแต่ละระดับ readiness | App reachable, DB ready, assets verified, model LOADED, protocol bound, inference qualified, queue/in-flight/deadline และ logging state ไม่รวมเป็น READY เดียว |
| OP-04 | Model services อยู่ตลอด promised session | ไม่ใช้ finite test listener ที่ cleanup ปิดเองระหว่างแพทย์ทดลอง; lifecycle และ native watchdog ต้องต่อกับ actual supervisor แล้ว |
| OP-05 | Bounded concurrency/queue/timeouts | เริ่ม execution ทีละงานตาม evidence; ระบุ queue capacity/admission, upload/prepare/execute/save/drain deadlines และพฤติกรรม busy/OOM/timeout ที่วัดได้ |
| OP-06 | Restart/reboot ฟื้นงานได้อย่างถูกต้อง | Labels/history/DB volumes/model identity คงอยู่; sent/uncertain request ไม่ถูก retry หรือ unlock จากเวลา/epoch ใหม่ |
| OP-07 | Stop เฉพาะสิ่งที่เป็นเจ้าของ | ตรวจ process/project identity, drain/terminal proof และ cleanup receipt; ไม่ kill บริการหรือ workloads ทีมอื่น ไม่ลบ DB/images/config |
| OP-08 | Installation และ offline dependencies ครบตาม profile | Packages/assets/weights มี inventory/hash/license boundary; normal startup ไม่ดาวน์โหลดและไม่ติดตั้ง dependency ใหม่ |
| OP-09 | Logs และข้อผิดพลาดใช้งานได้โดยไม่เปิดข้อมูลลับ | มี correlation, phase, safe error class และ timing; ไม่ echo token/DSN/PHI/raw exceptions ลง UI/evidence |

Persistent ในที่นี้หมายถึงบริการที่มีเจ้าของและใช้ได้ต่อเนื่องตาม session/operation contract ไม่ใช่สิทธิ์ใช้ GPU ไม่จำกัดเวลา งบที่อนุมัติยังมี hard limits การติดตั้ง system service/autostart ที่ต้อง privilege เป็น deployment approval แยก ต้องทดสอบ reboot path จริงและไม่อ้างจากไฟล์ systemd/Compose ที่มีอยู่เฉย ๆ

HANDOFF ยืนยันว่า **ยังไม่มี Hospital M1 start/status/stop recipe ครบที่ผ่านการทดสอบใหม่** คำสั่ง workstation เดิมและ model-server runbook เป็น foundation ไม่ใช่หลักฐานว่าชุด ordinary Hospital M1 พร้อมแล้ว

## 8. Backup, restore และ rollback

| ID | ข้อกำหนด | เงื่อนไขตรวจรับ |
| --- | --- | --- |
| RC-01 | Backup ครบข้อมูลที่กู้ workflow ได้ | PostgreSQL + immutable originals + workspace/release/migration/model identity และ private configuration references ตามนโยบาย; dataset export อย่างเดียวไม่พอ |
| RC-02 | Restore ไป isolated target ที่อนุมัติ | ปฏิเสธ source DB, occupied target, path collisions/redirects, missing/corrupt image hashes และ incompatible migrations โดยไม่ reset/drop ของเดิม |
| RC-03 | Guard-aware recovery ถูกต้อง | รักษา entry-guard dependencies/roles/fence semantics; ห้ามถอด guard เพื่อผ่าน app-schema-only backup |
| RC-04 | กู้แล้วใช้แอปได้จริง | Target environment/workspace ชัด, source-root reads ไม่เป็น fallback; original display/hash, SQL state, reopen/edit/export ตรงที่กู้ |
| RC-05 | Rollback รักษาข้อมูลแพทย์ | เลือก compatible validated release, คง previous assets และ DB; destructive restore over current data ต้องมี cutover approval แยก |

อ้าง [BACKUP_RESTORE.md](docs/operations/BACKUP_RESTORE.md) โดยตรง ไม่แต่งคำสั่ง one-click downgrade ใหม่ ขณะนี้ ordinary v2 rehearsal ผ่าน backup/restore และ engineering grade readback ใน synthetic scope แต่ export 409 และ hospital source recovery ไม่ผ่าน ส่วน Hospital M1 guard-aware recovery ยัง `NOT_QUALIFIED` ทั้งสองกรณีต้องไม่กลายเป็น PASS จากการตรวจ manifest offline

RPO/RTO และ retention ที่ sizing draft เสนอเป็น `TARGET_TO_QUALIFY` ไม่ใช่ SLA ที่ตกลงหรือวัดแล้ว ต้องให้ operational owner กำหนดและทดสอบกับขนาดข้อมูลจริงก่อนรับระบบ

## 9. สถานะปัจจุบันตามหลักฐาน

สถานะในตารางนี้ไม่ใช่เปอร์เซ็นต์งานรวม `DONE` หมายถึงจบในขอบเขตที่ระบุเท่านั้น `PARTIAL` คือมีของใช้ต่อได้แต่ยังไม่ครบ acceptance, `NOT_DONE` คือมีช่องว่าง implementation, `BLOCKED` คือ action/claim เฉพาะที่ยังไปต่อไม่ได้ และ `NOT_VERIFIED` คือรอบนี้ไม่มีหลักฐานพอยืนยันปัจจุบัน

| รายการ | สถานะ | หลักฐาน/สิ่งที่มี | ขอบเขตที่ยังขาด |
| --- | --- | --- | --- |
| Phase 1–4 foundations | DONE ตาม historical accepted scope | [Master plan](docs/milestone/m1/M1_MASTER_PLAN.md), [Phase 4 evidence](docs/milestone/m1/M1_PHASE4_EVIDENCE.md) | ไม่ใช่ Hospital M1/clinical/hospital-export acceptance |
| Local review/PG/export foundation | PARTIAL | Integrated source; historical C02 ใช้ actual UWF/CFP สองภาพกับ simulated AI | ไม่ใช่ actual-model E2E หรือ target install |
| Closed batch | DONE ใน batch scope | Re-read final/export receipts: 240 images, 480 terminal jobs, 467 PG readbacks; ledger hash ตรง | ไม่มี pending jobs ให้ replay; ไม่ใช่ GUI proof ทุกงาน |
| Deployment profile boundaries | PARTIAL | Main `deployment_profile.py` ตรวจ explicit profiles และ local endpoint fail-closed | Target runtime/offline/no-egress acceptance ยังขาด |
| Writer gate / DB fence / context foundations | PARTIAL | Main source, HANDOFF-reported SQL 12/12 และ actual context receipt PASS | Ordinary service binding/live GPU/native entry acceptance ยังขาด |
| New isolated credential roles | DONE ตาม recorded test scope; current ACL NOT_VERIFIED | Credential guide/HANDOFF รายงาน genuine password logins; directory/file metadata มีอยู่ | ไม่อ่าน secrets/receipt contents ใน private directory; ไม่ยืนยัน ACL ใหม่ในรอบนี้ และไม่ใช่ production identities |
| Combined candidate `8329c31` | 1.2: DONE — IN MAIN | Merge สะอาด (`83b3cd8`); อยู่ใน main `4ddb6a3`; main regression 1855 PASS / 67 SKIP | — |
| Remote candidate `6c0de66` | 1.2: DONE — REVIEW APPROVE, IN MAIN | Independent review APPROVE (68/68); merge `949cc5e` อยู่ใน main | — |
| Ordinary app factory binding | 1.2: PARTIAL (source + review fixes บน branch) | `a648b3d` ปิด 7 จุดตาม HANDOFF §5; review รอบแรก REQUEST_CHANGES → แก้ใน `4ddb6a3` (status probe ไม่อ้าง live, ต้องมี workspace เดิม, ต้องมี USPEC/RETFound พร้อม, token compare แบบ constant-time); focused 245 PASS; full 1851 PASS / 67 SKIP ที่ `a648b3d` | อยู่ใน main แล้ว (`4ddb6a3`, full 1855 PASS); composition จริงกับ PostgreSQL ที่อนุมัติ NOT_RUN; ยังไม่มี launcher เรียกใช้ |
| Native consumer/service assembly | 1.3: PARTIAL — live bounded session บน dr-train GPU0 ผ่านสำหรับ global grading (admission ก่อน dispatch, readback ก่อน admission ถัดไป, no retry, cleanup CONFIRMED); เป็น bounded acceptance runner ไม่ใช่ persistent service | HANDOFF §25, `COMPLETE.json` run `m1-server-20261023-01` | PRISM bound path ยังไม่เคยวิ่งจริงใน session; persistent operational service ยังไม่มี |
| No-code workstation launch | PARTIAL | Entry points, PG readiness/source controls และ historical startup evidence มีแล้ว | Complete two-profile package, cold/reboot/restart และ operational model lifecycle |
| Actual main-browser inference ครบสามโมเดล | 1.3: PARTIAL (2 จาก 3 โมเดล บน QA_SERVER) | USPEC 3 + RETFound 3 ผ่าน ordinary UI → actual model → PG readback → reopen หลัง restart (TEST_ONLY workspace, ภาพจริงจาก private roots) | PRISM BLOCKED ที่ preview attestation; export/physician label ยังไม่ทำ; QA_LOCAL NOT_RUN |
| Mask/reversible filtering | PARTIAL | Re-read PRISM measurement: 230 actual outputs, 65,639 raw / 8 proposed hidden / 3 UI | Chosen-stage GUI proof, adjudication, real-lesion loss และ clinician burden ยังไม่วัด |
| Training dataset / grading folders | PARTIAL | Export receipt: 240 records, 160 UNREVIEWED copies, 80 admission-skipped; DR/lesion labels 0 | Physician-confirmed target flow/rights and contamination proof; **1.2: owner decision ค้าง** — `services/dataset.py` อนุญาต export `HOSPITAL_AUTHORIZED` ในเครื่องเมื่อ identity ตรง แต่ `source_policy.py` และ §6 บอกว่ายังไม่อนุญาต; owner เลือกใช้ TEST_ONLY reviewer ไปก่อน |
| Backup/restore | PARTIAL / BLOCKED บางส่วน | Re-read QUALIFICATION: backup/restore/readback PASS, engineering grade 1 | Export BLOCKED 409; Hospital guard-aware recovery NOT_QUALIFIED; **1.2 วิเคราะห์แล้ว:** 409 เป็น frozen policy (v2 รับเฉพาะ WORKSPACE ซึ่ง export ถูกบล็อกเสมอ) ไม่ใช่ bug ของ restore; guard-aware recovery ต้องมี recovery contract ที่ owner อนุมัติแยก และ owner/admin DB credentials |
| Real consented images (1.2) | DONE ในขอบเขตการเตรียม | 21 ไฟล์ (UWF 11, CFP 10) คัดลอกแบบ byte ต่อ byte เข้า `M1PrivateConfig\hospital-roots`, hash ตรงทุกไฟล์, ผ่าน privacy check; ต้นฉบับ Desktop ไม่ถูกแตะ | ยังไม่ได้ admit ผ่านแอปหรือส่งเข้าโมเดล |
| QA Server target network | NOT_VERIFIED | Historical approved team route และ stopped runtime checkpoint ใน HANDOFF | ไม่ probe network ในงานนี้; hospital IT/data route approval และ target run ยังขาด |
| QA Local hospital target | BLOCKED_BY_TARGET / NOT_RUN | Hardware sizing เป็น draft | Machine/OS/driver/storage/offline inventory/operator และ onsite acceptance ยังไม่มี |
| Final packages/manual/gallery/HTML | NOT_DONE | Historical partial presentation และ retained screenshots มีอยู่ | Final release-specific dual-profile evidence/manual delivery ยังไม่ครบ |
| Lightning AI T4 comparison | NOT_RUN | มี historical T4 claims ใน deployment docs | ไม่มี equivalent actual comparison baseline ที่ตรวจใหม่ได้ในรอบนี้ |
| Clinical evaluation/accuracy/calibration | NOT_RUN / NOT_ESTABLISHED | Model/domain warnings มีอยู่ | ต้อง protocol/data/clinical reviewers และการอนุญาตแยก |

### 9.1 ตัวเลข batch ที่ reverify แล้ว

| Model | PASS_READBACK | FAILED_NO_RETRY | BLOCKED_PREMODEL |
| --- | ---: | ---: | ---: |
| USPEC (UWF grading) | 184 | 2 | 0 |
| RETFound (CFP grading) | 53 | 1 | 0 |
| PRISM (lesions) | 230 | 6 | 4 |
| รวม | 467 | 9 | 4 |

ภาพไม่ซ้ำ 240 = UWF 186 + CFP 54 ไม่ใช่จำนวนผู้ป่วย Request intents ใหม่ 476 + historical use 49 = 525; original jobs pending 0 หลักฐาน final batch เป็น snapshot `2026-10-23T04:31:34Z` และไม่ได้อ้างเป็น live service status ณ เวลาเขียน GOAL

Fresh SQL/hash verification 467 results และ source-image verification 240 เป็น **ผลเดิมที่ receipt บันทึกไว้** รอบนี้อ่าน receipt และตรวจ hash ของ ledger ไม่เปิด DB ใหม่ สาเหตุของ historical failures บางรายการยัง UNKNOWN ตาม [failure register](docs/planning/BATCH_THIRTEEN_TERMINAL_FAILURES_20261023.md) ห้ามกล่าวว่าแก้ครบจากการมี later pass

## 10. Acceptance matrix สำหรับสอง profiles

ต้องสร้างแถวผลแยก `QA_SERVER` และ `QA_LOCAL` ของแต่ละ ID พร้อม actual target/release/config identity ใช้ `PASS / FAIL / BLOCKED / NOT_RUN` และ reason/evidence pointer; fixture/control result ต้องมี evidence type ของมันเอง ห้ามกรอก PASS แทน live result

| ID | สิ่งที่ต้องพิสูจน์ | QA Server ณ snapshot | QA Local ณ snapshot | Evidence ที่ใช้ปิด |
| --- | --- | --- | --- | --- |
| AC-01 | Extract/install จาก versioned package พร้อม exact source/build/assets inventory | NOT_RUN สำหรับ final M1 | NOT_RUN บน hospital target | Manifest/checksums/install log และ target identity |
| AC-02 | No-code start, actual PostgreSQL readiness และ profile identity ถูกต้อง | PARTIAL foundation; final NOT_RUN | NOT_RUN | App/DB status, startup timing, SQL identity/readiness แบบไม่เผย DSN |
| AC-03 | Model assets/load/protocol พร้อมและ routes ตรง modality | 1.3: PARTIAL — CPU identity pins ตรง, RETFound/USPEC/PRISM load บน GPU0 ใน session; PRISM route ยังไม่ถูกใช้ | NOT_RUN | Per-model pins/device/load/capability/protocol receipts |
| AC-04 | Actual USPEC UWF inference ผ่าน ordinary app GUI | 1.3: **PASS (actual, TEST_ONLY)** — 3 requests fresh/restart/recovery, result digest ตรง PG readback (HANDOFF §25) | NOT_RUN | Request/result hashes, screenshot, actual model/phase/device และ persisted result |
| AC-05 | Actual RETFound CFP inference ผ่าน ordinary app GUI | 1.3: **PASS (actual, TEST_ONLY)** — 3 requests เช่นเดียวกัน; ภาพ CFP เป็นไฟล์ IDRiD ในโฟลเดอร์ consent ของ owner | NOT_RUN | หลักฐานชนิดเดียวกับ AC-04 ไม่ยืมผล USPEC |
| AC-06 | Actual protected PRISM inference ใน modality ที่อนุมัติ | 1.5: **PASS (actual, TEST_ONLY)** — PRISM 3 ครั้งผ่านหน้าแอป (CFP 1, UWF 2 แบบ experimental) → PG readback ผูก plan ครบ, เปิดกลับหลัง restart ได้, ทดสอบตัดการเชื่อมต่อแล้ว (HANDOFF §28) | NOT_RUN | Effective input/preview/entry proof/result/SQL และ experimental UWF notice |
| AC-07 | Physician grade/ROI edit → save → independent SQL readback | 1.6: **PASS (TEST_ONLY, local workstation)**: GUI แก้เกรด 3→2 และวาดกล่อง HEMORRHAGE แล้ว Finish; SQL แบบ READ ONLY ตรงกับที่ทำ (revision 9→13, geometry ใน original pixels, reviewer TEST_ONLY_ENGINEERING, annotation set hash คำนวณใหม่ตรง, inference history ไม่เปลี่ยน) ด้วย `scripts/qa/m1_local_acceptance.py`; หลักฐาน `M1PrivateConfig\evidence\m1-local-acceptance-20261024\`; กล่องวาดผ่าน scripted pointer events เพราะ drag tool ของ embedded browser ไม่ส่งถึง canvas | NOT_RUN | Revision/geometry/provenance และผู้ทดสอบจริงหรือ TEST_ONLY แยกกัน |
| AC-08 | Reopen/edit และ process restart/reboot ไม่สูญข้อมูล | 1.6: **PASS สำหรับ app restart (TEST_ONLY)**: restart เฉพาะ app 3 ครั้ง (health กลับใน ~13 วินาที, PostgreSQL ไม่ถูกแตะ) ทุก field ฝั่งแพทย์และ revision เท่าเดิม, เปิดกลับในหน้าจอเห็นเกรดและ finding เดิม, แก้หลัง reopen แล้ว restart ซ้ำก็คงอยู่; เดิมทุกครั้งที่ start แอปเขียน `admission.created_at/updated_at` ใหม่; owner อนุมัติให้แก้ → main `75d41f9`: `created_at` คงเวลารับภาพครั้งแรก, `updated_at` เปลี่ยนเฉพาะเมื่อเนื้อหา admission เปลี่ยน (ความหมายอื่นไม่เปลี่ยน); หลังแก้ restart แล้ว record ทั้งก้อนเหมือนเดิม (payload digest ตรง); และ main `9cde657` (owner อนุมัติ): rescan ไม่ล้าง `reviewed_by/reviewed_at/review_note` หลัง Confirm Image อีกต่อไป (ตรวจในแอปจริง restart 2 ครั้งยังอยู่ครบ; ผลข้างเคียงที่ดี: export ไม่ย้อนภาพที่ยืนยันแล้วกลับเป็น DRAFT ทุกครั้งที่เปิดแอป); reboot เครื่อง NOT_RUN | NOT_RUN | Before/after DB/case/source hashes, audit และ new invocation IDs เมื่อขอ AI ใหม่ |
| AC-09 | Export dataset + grading folders ตรงกับ authorized physician snapshot | PARTIAL; hospital permission gate คงอยู่ | NOT_RUN | Eligibility/contamination/hash comparisons และ approved destination |
| AC-10 | Original/mask/input/ROI stage ตรงกันและ suppression undo ใช้ได้ | 1.6: NOT_RUN บน workstation นี้: artifact ROI post-filter เป็น DISABLED ทุกเคส (ต้องมี provider/replay decision ต่อภาพจาก MS-06 ซึ่งยังไม่มี); AI ROI ที่กด Remove เป็นการตัดสินใจถาวรตามออกแบบ (409 เมื่อพยายามรับกลับ); restore มีเฉพาะ automated control tests (`artifactRoiAssist` frontend + backend) ไม่ใช่ GUI live | NOT_RUN | Gallery + GUI/save/reopen/undo + human adjudication แยก clinical claim |
| AC-11 | Network/API/auth unavailable หรือ interruption จบอย่างถูกต้อง | 1.6: PARTIAL+: แก้ป้าย "AI READY" ค้างแล้ว (main `061193a`): หน้า Review อ่านสถานะโมเดลใหม่ทุก 30 วินาที, เมื่อกลับมาที่หน้าต่าง และหลัง analysis ล้มเหลว; เห็นจริงในแอปว่าแสดง AI UNAVAILABLE เมื่อ dr-train ไม่เชื่อมต่อ; tunnel drop ระหว่าง requests (1.3) manual review ใช้ได้ ไม่มี charge ไม่มี fake result | NOT_RUN | Manual continuation, safe errors, ไม่มี fake results/retry หรือ data loss |
| AC-12 | Queue/body limits/timeouts/native watchdog/OOM/recovery มีขอบเขต | 1.6: PARTIAL (TEST_ONLY, local): stale revision → 409, body เสีย → 422, เคสไม่มี → 404, ขอ analysis ตอน Model API ไม่ถึง → 503 "AI analysis is not available; manual review remains available." ใน ~5.7 วินาที; SQL ก่อน/หลังยืนยันว่าเคสไม่เปลี่ยนและไม่มี inference entry ใหม่ (`M1PrivateConfig\evidence\m1-local-acceptance-20261024\ac12-failure-checks.json`); **gap:** review API ไม่มี request body limit ระดับแอป (มีเฉพาะ PRISM owned channel); queue/watchdog/OOM ต้องใช้ model host NOT_RUN | NOT_RUN | Controlled failure receipts, resource/timing และ no-replay proof |
| AC-13 | Backup + isolated guard-aware restore + app reopen/export | BLOCKED / NOT_QUALIFIED | NOT_RUN | Full DB/image/guard/migration identity และ target app evidence |
| AC-14 | Stop/status/restart ไม่กระทบ team workloads/volumes | 1.3: PARTIAL — bounded session stop: cleanup CONFIRMED, GPU0 คืน, GPU1/Ollama ไม่ถูกแตะ; final service NOT_RUN | NOT_RUN | Ownership/drain/cleanup และ retained-data proof |
| AC-15 | Profile data boundary | Hospital route NOT_VERIFIED | Offline run NOT_RUN | IT/data approval + backend route สำหรับ Server; offline/no-external-dependency evidence สำหรับ Local |
| AC-16 | Roles/private config/test-data isolation/audit | Test-role evidence partial | NOT_RUN | Actual runtime principal/privilege/privacy evidence โดยไม่บันทึก secrets |
| AC-17 | Versioned package/manual walkthrough/screenshots/HTML ตรง final release | NOT_RUN / incomplete | NOT_RUN / incomplete | ผู้ดูแลทำตามคู่มือได้จริง มี screenshots/timing จากผลจริง |

แต่ละ AC ต้องโยงกลับ WF/MK/DT/OP/RC ที่เกี่ยวข้อง ถ้ารายการ mandatory ยัง FAIL/BLOCKED/NOT_RUN จะไม่ประกาศ profile นั้น ready การมี profile หนึ่งผ่านไม่ทำให้อีก profile ผ่าน และห้ามเรียกผล public/synthetic engineering test ว่า physician UAT หรือ hospital acceptance

### 10.1 รูปแบบ evidence record ขั้นต่ำ

`acceptance_id`, `profile`, `result`, `evidence_type` (actual/control/fixture/document), UTC, source commit, served build, target/hardware, schema/migration, workspace/data snapshot ที่ไม่เปิดข้อมูลผู้ป่วย, model/preprocessing/mask identities, command/operation ID, observed timing, artifact pointer/hash, limitation, next actor

แยก `response observed`, `response retained`, `PG readback`, `accounting integrity` และ `evidence logging` ออกจากกัน HTTP 202/ADMITTED ไม่ใช่ terminal completion และ log เขียนไม่สำเร็จไม่ใช่หลักฐานว่า model หรือ DB ล้มเหลวตามไปด้วย

## 11. Credentials, roles และ access ที่ต้องอธิบายให้ตรง

รายงานเก่า `M1_ACL_READONLY_FINDINGS_20261023.md` ระบุว่า `local-state/release` และ `postgres.env` มี inherited Allow เพิ่มสี่รายการ แต่ละรายการมี Modify/Synchronize ใช้กับ object จริง สามรายการเป็น unresolved SIDs อีกหนึ่งเป็น `DESKTOP-C8EHASQ\CodexSandboxUsers` ไม่ใช่หลักฐานว่ามี unrelated humans สี่คน หรือมี secret ถูกอ่าน ไม่พบ Everyone/Authenticated Users ในสี่รายการนั้น ตัว checker ปฏิเสธเพราะนอก allowlist

เอกสารใหม่ [M1_TEST_CREDENTIALS.md](docs/operations/M1_TEST_CREDENTIALS.md) และ HANDOFF §8 รายงานการอนุมัติ dedicated directory `C:\Users\User\AppData\Local\DRScreening\M1PrivateConfig` แยกจาก directory เก่า และ genuine runtime/authority password logins ผ่านเมื่อ 09:08 UTC รายงานนี้เป็น **recorded scoped qualification** ไม่ใช่การยืนยัน ACL ปัจจุบันใหม่ของผู้เขียน GOAL

- ไม่แสดง secret DSNs/tokens/passwords หรืออ่าน `.env` เพื่อเติมเอกสาร
- ไม่ใช้ checker failure เป็นสิทธิ์ย้าย secrets, ผ่อน checker, แก้ inheritance หรือเพิ่ม grants เอง
- Runtime, authority และ NOLOGIN owner เป็น test objects คนละหน้าที่ ไม่อ้างว่าเป็น hospital production access model ที่รับรองแล้ว
- อย่ารัน one-shot provisioning ซ้ำ, reset passwords หรือ drop roles/DB เพราะชื่อ/ไฟล์มีอยู่แล้ว
- Linux model token/private permissions และ Tailscale route เป็นอีก boundary หนึ่ง Windows config issue ไม่ใช่เหตุให้สร้าง Linux credentials หรือ server ใหม่
- Role/access ที่เหมาะกับ physician workflow ต้องรับรองตาม actual target; ไม่เพิ่ม SSO/multiuser product scope โดยไม่มีข้อกำหนด แต่ต้องไม่กล่าวว่า reviewer-name field เท่ากับ authenticated identity

การเปลี่ยน security-sensitive ต้องขอแบบ action-specific ระบุ target, principal/rights, impact และ rollback ที่คงข้อมูลเดิม หาก actual access/security/privacy gate ปฏิเสธ ให้หยุด action นั้น ไม่เปลี่ยน tool/path/transport เพื่อข้าม แล้วทำงานอิสระที่ยังอยู่ในสิทธิ์ต่อได้

## 12. การทบทวนความถูกต้องของ HANDOFF

**ข้อสรุป:** HANDOFF.md ล่าสุดจับเป้าหมาย Hospital M1 สอง profiles ได้ถูก และเตือนว่า M1 ยังไม่เสร็จแล้ว GOAL นี้ทำให้เป้าหมาย, acceptance และลำดับปิดงานละเอียดขึ้น โดยไม่แก้ HANDOFF หรือเปลี่ยนสถานะผลเดิม

| ประเด็น | HANDOFF / เอกสารเก่า | การตีความที่ใช้ต่อ |
| --- | --- | --- |
| Hospital M1 vs demo | HANDOFF เริ่มด้วย two usable QA profiles และ actual physician/data flow; บางตอนยังใช้คำว่า demo/session | Session เป็นเพียง operating envelope; final milestone ต้อง deployable และใช้ทดลองจริง ไม่จบที่ finite demo |
| Source revision | HANDOFF ระบุ main implementation `7be279d` และคาดว่าจะมี doc successor | ตรวจได้ successor `49ad62f`; ไม่ถือ candidate ใหม่กว่าเป็น integrated main |
| Batch complete | 480 terminal jobs resolved | รักษาผล batch และ defects ที่เหลือ; ไม่เปิดทั้ง batch ใหม่เพื่อพิสูจน์ GUI |
| Compute cap | Spec/early handoff ยังมี 525/529; latest proposal/HANDOFF ระบุ 549 | ใช้ historical cap ตามประวัติ และ later approved cap549 แบบ NOT_ACTIVATED สำหรับ scope ใหม่ ไม่แก้ ledger ให้ดูว่าอนุมัติมาตั้งแต่ต้น |
| Credentials | Early report ยังเสนอ private directory; latest guide/HANDOFF รายงาน applied/login PASS | แยกเวลาของหลักฐานและขอบเขต; รอบนี้ metadata-only ไม่มี current ACL PASS ใหม่ |
| Mask | Retained post-filter/undo มีจริง แต่ไม่ใช่ pre-mask | Mask ยังคงเป็น M1; ประเมิน false ROI และ true-lesion loss ไม่อ้าง proven improvement |
| Service readiness | Ordinary factory/native lifecycle ยัง unfinished | Health/load/source tests และ finite listener ไม่ปิด operational acceptance |
| QA Local | Target hardware ยังไม่มี qualification | ไม่เอา team-host run หรือ synthetic Compose smoke มาแทน onsite offline acceptance |
| Historical Phase 5/manual option | Candidate plan เคยอนุญาต manual product ถ้า owner รับ scope | Latest Hospital M1 ต้องมี real modalities/models ตาม AC; manual mode เป็น fallback ไม่ใช่ลด acceptance เงียบ ๆ |
| Export/recovery | Existing hospital export fail-closed และ guard-aware backup ไม่ผ่าน | เป็น release dependencies ที่ต้องปิดด้วย approved contract/implementation ไม่แก้ชื่อ origin หรือถอด guard |
| T4 | บาง deployment docs รายงาน historical synthetic single-T4 smoke | เก็บเป็น reported historical scope; same-workload T4 comparison ยัง NOT_RUN ไม่แต่ง timings |
| ความคืบหน้า 50% | HANDOFF บอกเป็น subjective engineering estimate | ไม่ใช้ใน acceptance หรือคิดเปอร์เซ็นต์ใหม่จาก test counts |

Historical public Pepo handoff และ external CLI packet มี snapshot เก่ากว่า HANDOFF ล่าสุด ข้อห้ามการ replay, privacy, GPU และการรักษา owner artifacts ยังคงใช้ แต่สถานะ cap/credentials/source ต้องดูหลักฐานใหม่กว่าที่ระบุชัด ไม่ตีความข้อความ “not production authorized” ในเอกสารเก่าเป็นเหตุให้เลิกทำ deployable engineering package หรือใช้ latest owner intent เป็นใบอนุญาต clinical deployment

## 13. งานที่เหลือ ลำดับความสำคัญ และ dependencies

ลำดับนี้ใช้ **หลัง owner อนุญาตให้ engineering ทำต่อ** ไม่ใช่คำสั่งเปิดงานในรอบ documentation นี้ แต่ละงานต้องรักษาของเดิมและปิด defect ที่มีหลักฐานก่อนเพิ่ม audit รอบกว้าง

| ID / Priority | ผลลัพธ์ที่ต้องได้ | Dependencies | เกณฑ์ออก / ผู้รับผิดชอบ |
| --- | --- | --- | --- |
| MS-01 / P0 | Source ownership/integration checkpoint ตรงจริง | Current main/candidate/WIP, Git access ที่ถูกต้อง | VS Code Codex ตรวจ exact ancestry/diff, คง WIP/untracked, ปิด pending remote delta review และ integrate เฉพาะที่ผ่าน gates |
| MS-02 / P0 | Ordinary app factory/context/preview/provider binding ครบ | MS-01, existing authority/fence contracts | ไม่มี undefined owned connection; bind reader ครั้งเดียว, register preview ก่อน routes, preserve USPEC/RETFound; focused controls/review ผ่าน |
| MS-03 / P0 | Actual operational model lifecycle/native consumer | MS-02, supervisor/ACK/status/result/readback adapters | Start/status/stop, watchdog/queue/ownership/quarantine/accounting ต่อกับ actual child; ไม่ใช้ temporary listener เป็นบริการส่งมอบ |
| MS-04 / P0 | Durable approved continuation พร้อมใช้อย่างถูกต้อง | MS-03 และ current ledger/approval anchors | Exact operation IDs/source/model pins/window/clock/owner ลง durable state ก่อน dispatch; ยังไม่เริ่ม GPU เพียงเพราะ manifest สร้างแล้ว |
| MS-05 / P1 | QA Server ordinary-main E2E | MS-01–04, authorized route/data และ integrated served build | AC-03–12 ตาม scope พร้อม actual screenshots/SQL/reopen/export; no retries/terminal replay |
| MS-06 / P1 | Mask comparison และ physician review | Retained outputs ทำส่วน offline ได้ทันทีเมื่อ resume; GUI ต้องใช้ integrated build | MK-01–07, gallery, adjudication/unknowns และ clinician cleanup evidence; ไม่ต้องรอ rerun batch |
| MS-07 / P1 | Guard-aware backup/restore และ export authority gap ปิด | Recovery contract, DB/IT/data-owner decisions ที่ตรง action | RC-01–05, actual isolated rehearsal/reopen/export; คง rejection จนแก้ได้ถูกขอบเขต |
| MS-08 / P1 | QA Local target/offline acceptance | IT ระบุ target/storage/driver/assets/access; source/package ทำอิสระได้ | All-local normal operation/cold restart/reboot, shared accounting adoption และ AC ทุกข้อบน actual target |
| MS-09 / P1 | Final release package/manual/presentation | MS-05–08 ตาม profile; packaging ทำคู่ขนานในแง่ลำดับงานได้โดย sole writer | Version/checksums/templates, actual walkthrough/evidence, known limitations และ owner/operator review |

“งานอิสระทำได้” ไม่ได้อนุญาตเพิ่ม application-code writer: VS Code Codex ยังเป็นผู้เขียนโค้ดรายเดียว การอ่าน/review/เขียนเอกสารต้องไม่แย่ง ownership หรือแก้ shared files พร้อมกัน

### 13.1 Dependency ที่ต้องถามเมื่อถึง action นั้น

- **IT/data owner:** QA Server อนุญาต route และ image transfer ใด; ถ้าไม่ได้ให้เลือก offline QA Local โดยไม่เปลี่ยน network เอง
- **Hospital operator:** เครื่อง QA Local จริง, OS/GPU/driver, storage, offline delivery method, service owner และ maintenance window
- **Data/clinical owner:** Hospital export destination/scope และ reviewed/adjudicated gold/negative policy ที่ยังไม่ตกลง; ห้ามนิยามแทนแพทย์
- **Operational owner:** Expected session/concurrency/queue, retention/RPO/RTO และ response-time targets ก่อน final qualification ไม่ตั้ง SLA จาก historical p95
- **Security/IT:** เฉพาะสิทธิ์/service account/ACL/autostart/persistent access ที่จำเป็นและยังไม่ได้อนุมัติ พร้อม target/impact ชัด

ข้อมูลเหล่านี้เป็น pending deployment/clinical decisions ไม่ต้องเดาใน GOAL และไม่ต้องให้ owner อนุมัติ routine engineering ทีละไฟล์ หากพบ conflict ที่เปลี่ยน clinical/security/frozen semantics ให้หยุดเฉพาะทางเลือกที่พึ่งการตัดสินใจนั้นและถามก่อนเขียน implementation

## 14. กติกาการทดสอบและงบทรัพยากร

### 14.1 ใช้หลักฐานเดิมให้คุ้ม

- ใช้ [terminal failure register](docs/planning/BATCH_THIRTEEN_TERMINAL_FAILURES_20261023.md) ระบุ defect/unknown/repair ที่เล็กที่สุด ไม่เริ่ม broad audit หรือ 480-job batch ใหม่
- Focused tests ต้องตรง changes และ meaningful failure modes จากนั้นทำ required branch/main checks ตาม AGENTS หลัง integration ไม่ rerun unchanged passing suite วนเพื่อเพิ่ม test counts
- Synthetic fixtures/controlled clocks/children ใช้พิสูจน์ controls; actual model/PG/browser/hospital target และ clinical validation ต้องแยกผล
- ไม่เปิด permission-mutation fixtures เป็นค่าเริ่มต้นหรือปรับ ACL ใน tests เพื่อเอา PASS; skips ต้องรายงาน ไม่รวมกับ passes
- ทดสอบ network/model/DB/logging failure ใน isolated approved context ห้ามรบกวน workloads ทีมอื่นหรือใช้ real physician data แทน fixtures โดยไม่ได้อนุญาต
- งาน documentation นี้ตรวจเฉพาะ readback/diff/links/consistency ไม่เรียก tests/build/checkers ที่มี side effects

### 14.2 Approved compute ที่ยังไม่ activate

| รายการ | ขอบเขตตาม latest approved proposal |
| --- | --- |
| Historical used / old cap | 525 / 529; original terminal states และ historical49 คงเดิม |
| Latest approved cumulative cap | 549; เพิ่ม20 รวม old remaining4 เป็น24 available ตาม exact scope ไม่ใช่คำสั่งให้ใช้ให้หมด |
| QA Server | 9 requests: fresh3 + restart3 + explicit failure/recovery3 |
| QA Local | 6 requests: fresh3 + restart3 บน target ที่มีจริงและอนุมัติ |
| Post-fix verification | 9 new separately scoped intents อ้าง historical failures หลังมี concrete repair; ไม่ resubmit old jobs |
| Initial mask comparison | 0 new requests ใช้ retained230 PRISM outputs |
| Named windows | ไม่เกินสองช่วง: `HOSPITAL_M1_QA_SERVER_20261023`, `HOSPITAL_M1_QA_LOCAL_20261023` |
| Time limits | แต่ละ window GPU0 ≤10,800s และ wall ≤14,400s; total new reservation ≤6 GPU-hours |
| Activation | `OWNER_APPROVED / NOT_ACTIVATED` ตาม HANDOFF; exact24 operation manifest/live assembly ยังไม่ materialized/qualified |
| 1.3 สถานะใช้จริง | proposal v2 `5a06f23c…` activated; Server window **ปิดถาวร** used 525 → 531; เหลือ 18 (QA_LOCAL 6, post-fix 9, Server PRISM 3 ที่ไม่มี window เปิด — ต้อง owner อนุมัติ window ใหม่) |

อ่าน [proposal ฉบับเต็ม](docs/planning/HOSPITAL_M1_GPU_REQUEST_PROPOSAL_20261023.md) ก่อนใช้สิทธิ์ Runtime ต้อง durable-charge ก่อน dispatch ไม่มี automatic retry, renew, refund/reset clocks หรือ replay sent/uncertain jobs สถานะไม่แน่ชัดต้องรักษา quarantine และ lower-bound usage ไม่ทำเป็นศูนย์

ใช้เฉพาะ approved team **GPU0 RTX 2080 Ti**, UUID `GPU-044a8b11-4729-458b-a07b-297e45439419` ไม่ใช้ GPU1 V100/Ollama การรับเครื่อง QA Local ใหม่ต้องผูก actual approved identity ของมันแยก ไม่ถือ team GPU permission ครอบคลุม hardware อื่น

Historical conservative reservations 4,772.230 + 9,800.644 + stopped preload 2,430.000 = 17,002.874s เป็นค่าข้าม sessions ไม่ใช่ GPU kernel occupancy หรือ latency benchmark Preload observed 521.948s/zero inference ไม่ทำให้ reservation เดิมถูกคืน

หาก scope/time/requests ไม่พอ ให้เสนอส่วนเพิ่มแบบเจาะจงครั้งเดียวพร้อมเหตุผลและงานอิสระที่ทำต่อได้ ห้ามเปลี่ยน accounting หรือใช้ compute approval แทน data/network/security approval

## 15. Hardware และการวัด performance

ใช้ [hospital sizing draft](docs/planning/HOSPITAL_LOCAL_QA_MIN_MAX_DRAFT_TH_20261023.md) เป็น **planning input** เท่านั้น ข้อเสนอเริ่มต้น GPU host 8 cores/RAM32GB/GPU12GB/NVMe1TB และ upper QA 16 cores/RAM64GB/GPU24GB/NVMe2TB ยังไม่ใช่ minimum ที่พิสูจน์แล้วหรือใบสั่งซื้อ และ upper configuration ยังไม่อนุญาตเพิ่ม concurrency

สิ่งที่มีคือ retained sequential RTX2080Ti 11GB workload, 117 lease resource receipts, sampled PRISM maximum 5,442MiB และ worker-only RSS ราว2.43GiB ไม่ใช่ host/process-tree peak หรือ simultaneous model residency หลักฐาน historical passed PRISM whole-job p95 ราว81.422s/max109.375s ไม่ใช่ native execution deadline หรือ promised interactive SLA

ก่อนตั้ง capacity/SLA ต้องบันทึก workload/denominator, cold/warm conditions, queue/upload/prepare/execute/save/readback timings, p50/p95/max เมื่อจำนวนตัวอย่างพอ, CPU/host RAM/VRAM, disk/LAN และ failure rates แยกต่อ profile/target อย่านำ C02 cold กับ main warm หรือ DB-only span ไปเปรียบว่า hardware เร็วกว่า

**Lightning AI T4 16GB:** การเปรียบเทียบ equivalent workload ยัง `NOT_RUN` Historical docs ที่รายงาน T4 smoke เป็น reported hardware/runtime evidence ในขอบเขตนั้น ไม่ใช่ measured comparison กับ dr-train ถ้า actual baseline/runtime inventory ไม่พร้อม ให้คง pending และไม่แต่ง benchmark numbers

## 16. Operational readiness แยกจาก clinical evaluation

| มิติ | ต้องใช้อะไรตัดสิน | สิ่งที่ใช้แทนไม่ได้ |
| --- | --- | --- |
| Engineering/product | Integrated app, UI/save/reopen/export/source/coordinate invariants | Planning checklist หรือ model metadata |
| Operational | Installation/lifecycle/reboot/offline/roles/privacy/backup-restore บน target | Health200, มี Compose/systemd file หรือ historical finite QA run |
| Model runtime | Actual pinned capability/load/inference/response/device และ modality | Weight hash อย่างเดียว, fixture output หรือ LOADED ที่ไม่มี forward |
| Physician usability/UAT | ผู้ใช้ที่ได้รับมอบหมายทำงานจริง พร้อม defects/timing/feedback | Developer walkthrough หรือ engineering TEST_ONLY label |
| Clinical/model evaluation | Protocol/data/rubric/reviewer/adjudication และ metrics ที่ได้รับอนุญาต | ROI suppression count, softmax score, E2E pass หรือจำนวน tests |

USPEC rights/model-use permissions และ PRISM UWF experimental/`NOT_VALIDATED_FOR_UWF` ต้องคงข้อจำกัดตามหลักฐานล่าสุด ไม่ถือ technical load/inference เป็น rights approval หรือ UWF clinical validation ไม่แสดง attention เป็น lesion localization หรือ confidence เป็น calibrated probability

Supervised trial ต้องระบุ data scope, physician responsibility, access และ known limitations ให้ผู้ใช้ทราบ การรับ operational M1 ไม่ปิด clinical evaluation โดยอัตโนมัติ

## 17. ความเสี่ยงและการตัดสินใจที่ต้องเก็บไว้

| ID | ความเสี่ยง/ข้อค้าง | ผลกระทบและทางปิด |
| --- | --- | --- |
| RK-01 | Candidate/WIP/main ต่าง revision | ห้าม serve/merge เพียงเพราะใหม่กว่า; ตรวจ dependencies และ source/build identity ก่อน acceptance |
| RK-02 | Native request outcome ไม่แน่ชัดหรือ service ดับ | คง durable accounting/quarantine, authenticated old-job proof และ no-replay; ไม่ TTL unlock |
| RK-03 | Closed VLAN เข้า team server ไม่ได้ | QA Server target BLOCKED เฉพาะ route; เตรียม QA Local/offline package ต่อโดยไม่แก้ network |
| RK-04 | Guarded DB กู้ด้วย app-schema dump ไม่ครบ | RC-03 เป็น release blocker; qualified recovery contract/rehearsal ไม่ถอด trigger/guard |
| RK-05 | Mask ซ่อน true peripheral lesions | Preserve raw/uncertain/undo และ human adjudication; ถ้ายังไม่วัดให้รายงาน unknown/retain-all ตาม policy |
| RK-06 | Physician/test/raw AI ปน training labels | Workspace/reviewer/provenance/export eligibility และ data-snapshot contamination checks |
| RK-07 | Credentials/privacy status ถูกอ้างเกินจริง | แยก historical receipts, current metadata และ actual privacy check; อย่าเปลี่ยนสิทธิ์เพื่อให้เอกสารดูผ่าน |
| RK-08 | Provider environments/weights/rights ไม่ตรง target | Exact inventory/pins/security applicability ก่อน load; ไม่ install generic latest ทับ environment ที่ qualified |
| RK-09 | Historical viewer/HTML access denial และ workspace docs hygiene failures | คืน execution/access ผ่านช่องทางอนุมัติ; preserve owner archives; ไม่เปลี่ยน route/checker หรือลบไฟล์ให้ผ่าน |
| RK-10 | ภาพ/HTML/manual เผยข้อมูลหรือไม่ตรงผลจริง | ใช้ authorized sanitized evidence, actual screenshots และ release-bound walkthrough; ไม่แต่งภาพ/paths |

Historical denied composite runtime-summary/HANDOFF/log writes ที่ HANDOFF §18 บันทึกไว้ยังหยุดอยู่ GOAL.md ที่ owner ขอใหม่นี้ไม่ retry actions เหล่านั้น การเขียน log ไม่ได้ไม่ควรถูกเรียกว่า model failure และ blocker ของ viewer/log/IT ไม่ควรถูกเหมารวมว่าทั้งโครงการทำอะไรต่อไม่ได้

## 18. สิ่งส่งมอบและ Definition of Done

| ID | Deliverable | เงื่อนไขรับ |
| --- | --- | --- |
| DL-01 | Versioned deployable release package | Source/release commit, build identity, manifest/checksums, dependencies และ change/known-limitations record ตรงกัน; ไม่มี secrets/PHI/runtime DB/weights ปนใน software archive |
| DL-02 | QA_SERVER และ QA_LOCAL templates สองชุดไม่มี secrets | Explicit profile, storage/DB/model references และ instructions ใส่ private values; offline assets จัดส่งแบบ controlled inventory แยกจาก Git/archive ที่ห้ามบรรจุ |
| DL-03 | No-code installation/start/status/stop | Canonical launchers เดิมและ model-host procedures ใช้ได้ตาม installed target, database readiness/reboot recovery และ ownership ชัด |
| DL-04 | Maintenance/backup/restore/rollback guide | ทดสอบกับ actual guarded DB/images/target, compatibility/partial failure/recovery steps และผู้รับผิดชอบ |
| DL-05 | E2E matrix + actual evidence | AC ทุกแถวสอง profiles พร้อม revision/type/result/artifact/timing, screenshots/SQL/hash proof และ explicit NOT_RUN/BLOCKED |
| DL-06 | Mask comparison gallery | Before/after actual PRISM, stage/parameters/raw/hidden/undo/uncertain และ human adjudication/limitations ไม่อ้าง clinical gain เกินข้อมูล |
| DL-07 | HTML team presentation และคู่มือ deployment ภาษาไทย | อธิบายเป้าหมายสอง profiles, architecture/data flow, actual results/failures, owner/operator steps; assets มาจากผลจริงและเปิดผ่านช่องทางที่อนุมัติ |
| DL-08 | Manual deployment walkthrough กับผู้ดูแล | ผู้ดูแลทำตาม final package ตั้งแต่ install/start ไปถึง restore/export ได้ พร้อม actual feedback/blockers และข้อมูลที่ไม่เปิดความลับ |

**Hospital M1 DONE** ต้องมีทุกข้อดังนี้:

1. Integrated source ผ่าน review/validation/lifecycle ตาม AGENTS และ served build ตรง release; คง owner artifacts และ single-writer arrangement
2. QA Server และ QA Local มี target-specific acceptance ครบ requirement ที่จำเป็น พร้อม operational ownership และสิทธิ์ข้อมูล/เครือข่ายที่เหมาะสม
3. Actual modality-appropriate USPEC/RETFound/PRISM ผ่าน ordinary user flow; save/independent SQL/reopen/edit/export และ mask stage/undo ตรวจจริง
4. No-code cold start/reboot/restart/failure recovery, bounded service lifecycle และ tested guard-aware backup/restore ใช้ได้โดยไม่ทำลายข้อมูลเดิม
5. Dataset lineage/physician separation, secret-safe configuration, immutable originals และ source/export privacy policies ผ่าน
6. DL-01–08 ครบ มี actual screenshots/timing และ honest limitations; owner/operator/clinical reviewer รับเฉพาะหมวดที่ตรวจจริง

ถ้าเครื่อง QA Local หรือ hospital export permission ยังไม่มี ให้ส่ง `READY_FOR_REVIEW / PARTIAL` ของส่วนที่ทำได้พร้อม blocker และ next actor ไม่ใช้ DONE ทั้ง milestone หรือเอา planning document มาแทน target evidence Clinical validation อาจยัง NOT_RUN ตามขอบเขต M1 แต่ต้องสื่อชัดและห้ามอ้าง clinical readiness

Commit/push/merge เป็นงานของ implementation owner ในช่วงที่ได้รับอนุญาตตาม AGENTS งานเขียน GOAL นี้ไม่ commit/push/merge และไม่ได้ทำให้ engineering ที่ pause อยู่กลับมาทำงานเอง

## 19. วิธีที่ implementation agent ต้องอัปเดต GOAL

- อ่าน current GOAL/HANDOFF/Git state ก่อนเขียนทุกครั้ง ถ้าไฟล์กำลังเปลี่ยนหรือ hash ไม่ตรง preimage ให้หยุดการเขียนทับและรายงาน ไม่ restore/stash/clean งานผู้อื่น
- รักษา stable requirement/acceptance IDs เดิม อัปเดต fact/status/evidence/next actor เป็นหลัก ไม่ออกแบบ scope ใหม่ทุก turn และไม่สร้าง orchestration/launcher framework ใหม่เพื่อแทนของที่มี
- เมื่อปิดงาน ให้ระบุ exact revision, actual execution scope, target, data snapshot, artifact/hash และข้อจำกัด เปลี่ยนเป็น DONE/PASS เฉพาะแถวที่มีหลักฐานถึงเกณฑ์
- แยก source control tests, fixtures, actual model, actual PostgreSQL, browser, hospital target และ clinical outcomes; ไม่รวม test counts ข้าม revisions หรือเปลี่ยน skipped/N/A เป็น PASS
- เก็บ historical values/receipts ไว้พร้อมเหตุผลที่ supersede เพิ่ม dated update log แทนการแก้ประวัติให้ดูว่าผ่านมาตั้งแต่ต้น
- ถ้าต้องเพิ่ม scope/model/threshold/policy/สิทธิ์ ให้บันทึก decision ที่เจาะจงและ authority ของการอนุมัติ การสร้าง proposal เองไม่ใช่ owner approval
- เมื่อ blocker เป็นเฉพาะ action ให้รายงาน action/target/reason/executed-or-not/next actor แล้วทำ independent authorized work ต่อ เมื่อ goal-critical ambiguity กระทบ frozen/clinical/security contract ให้ถามก่อนเลือกทาง

### 19.1 Update log

| UTC/date | Revision | การเปลี่ยนแปลง | หลักฐาน/ผู้รับช่วง |
| --- | --- | --- | --- |
| 2026-10-23 | GOAL 1.0 | จัดเป้าหมาย latest owner intent, สอง profiles, stable requirements/acceptance, reconciled HANDOFF, remaining delivery gates | Read-only project/receipt review ที่ main49ad62f; engineering ยัง pause และ VS Code Codex เป็น sole application-code writer |
| 2026-10-23T10:53Z | GOAL 1.1 | ตรวจซ้ำแบบอ่านอย่างเดียวตามคำขอ owner: Git/remote, candidate heads, WIP worktree, hashes และ listeners; เพิ่ม HANDOFF §22; บันทึก worktrees ที่ไม่อยู่ในตาราง HANDOFF ซึ่ง commits เทียบเท่าที่อยู่ใน main แล้ว (`git cherry`) แต่ยังไม่ลบ | Claude Code, documentation-only, ไม่ commit; ไม่รัน tests/builds/inference/SSH/DB; **ไม่มีสถานะใน §9/§10 เปลี่ยน**; engineering ยัง pause |
| 2026-10-23 (หลัง 10:53Z) | GOAL 1.2 | owner สั่งทำงานต่อ: Claude Code เป็น sole writer; MS-01 รวม `8329c31` + `6c0de66` บน branch; MS-02 composition + review fixes (`a648b3d`, `4ddb6a3`); คัดลอกภาพจริงเข้า private roots; วิเคราะห์ MS-03/MS-07; merge เข้า main ถูก permission check ปฏิเสธ | Claude Code; หลักฐานใน HANDOFF §23; สถานะใน §9 อัปเดตเฉพาะแถวที่มีหลักฐาน; ไม่มี GPU/inference/SSH |
| 2026-10-24 | GOAL 1.6 | UX ระยะ A + sidebar/ภาพใหญ่ + แก้ AI READY ค้าง (merge main `e52863d`, `ca5e3bd`, `061193a`); local TEST_ONLY evidence AC-07 PASS, AC-08 app-restart PASS, AC-12 PARTIAL, AC-10 NOT_RUN; tool `scripts/qa/m1_local_acceptance.py` | Claude Code; HANDOFF §29-§30; admission timestamp แก้แล้ว `75d41f9`, ผู้ยืนยันภาพไม่ถูกล้าง `9cde657`; ผู้รับช่วง: owner reboot test, export decision |
| 2026-10-24 | GOAL 1.5 | PRISM GPU window (owner อนุมัติแผน + hash v3): 3/3 PASS_READBACK, window ปิด 534/534; พบ UI defect เรื่อง quality ต้องเป็น GRADABLE ก่อน PRISM; แก้ log/readback merge main `d5a3102` | Claude Code; HANDOFF §28 |
| 2026-10-24 | GOAL 1.4 | Recorded source identity amendment (owner อนุมัติ): Part A + Part B merge main `f4e943d`; backup ก่อน แล้ว apply 27 เคส TEST_ONLY readback PASS; AC-06 จาก BLOCKED เป็น NOT_RUN รอ GPU window | Claude Code; HANDOFF §26 |
| 2026-10-23T13:04Z | GOAL 1.3 | QA_SERVER live session ตามคำสั่ง owner: global grading 6/6 PASS_READBACK, PRISM 0/3 (preview attestation gap = STOP item), post-fix ไม่รัน, window ปิดถาวร (531/549); แก้ launcher/app 5 จุดและ merge main `d7ca474` | Claude Code; HANDOFF §25; AC-04/05 QA_SERVER PASS (TEST_ONLY), AC-06 BLOCKED; ผู้รับช่วง: owner ตัดสินใจ PRISM attestation amendment และ window ใหม่ |

## 20. Evidence index และขอบเขตการอ้างอิง

### 20.1 เอกสารใน repository

| Ref | เอกสาร | ใช้เป็นอะไร |
| --- | --- | --- |
| E-01 | [AGENTS](AGENTS.md), [DESIGN](DESIGN.md), [README](README.md), [quick start](README_START_HERE.md) | Instructions, protected workflow และ operating foundation; ไม่ใช่ fresh target PASS |
| E-02 | [HANDOFF](HANDOFF.md) | Latest paused checkpoint, source/candidates/permissions/reviews/remaining tasks |
| E-03 | [Hospital M1 spec](docs/milestone/m1/HOSPITAL_M1_RELEASE_CANDIDATE_SPEC.md), [mutable PRISM authority](docs/milestone/m1/M1_MUTABLE_PRISM_ENTRY_AUTHORITY.md) | Acceptance/implementation contracts ไม่ใช่ execution receipts |
| E-04 | [GPU proposal](docs/planning/HOSPITAL_M1_GPU_REQUEST_PROPOSAL_20261023.md) | Recorded owner-approved cap549 และ exact scope; NOT_ACTIVATED |
| E-05 | [13 terminal jobs](docs/planning/BATCH_THIRTEEN_TERMINAL_FAILURES_20261023.md) | Retained diagnostic analysis, unknowns และ targeted repair boundaries |
| E-06 | [Master plan](docs/milestone/m1/M1_MASTER_PLAN.md), [Phase 4 evidence](docs/milestone/m1/M1_PHASE4_EVIDENCE.md), [Phase 5 plan](docs/milestone/m1/M1_PHASE5_E2E_VALIDATION.md) | Historical accepted phases แยก prospective Phase5 acceptance |
| E-07 | [Installation](docs/operations/INSTALLATION.md), [deployment](docs/operations/DEPLOYMENT.md), [dual-mode](deployment/dual-mode/README.md) | Architecture/runbook/package foundations; target-specific qualification ต้องเพิ่ม |
| E-08 | [Recovery](docs/operations/BACKUP_RESTORE.md), [credentials](docs/operations/M1_TEST_CREDENTIALS.md), [security](docs/operations/SECURITY_PRIVACY.md) | Recovery/access boundaries, documented scoped results และ current guard limitation |
| E-09 | [Clinician manual](docs/manuals/clinician/index.qmd), [dataset manifest](docs/reference/DATASET_MANIFEST.md), [release checklist](docs/release/RELEASE_CHECKLIST.md) | Workflow/export contract และ release requirements; unchecked checklist ไม่เป็น PASS |
| E-10 | [Sizing draft](docs/planning/HOSPITAL_LOCAL_QA_MIN_MAX_DRAFT_TH_20261023.md), [public Pepo handoff](docs/developer/PEPO_GPT_DOT_HANDOFF_20261023.md) | Historical facts/planning assumptions; status ใหม่ดู E-02/E-04 |
| E-11 | [Main factory](dr_support/api/_factory.py), [preview runtime](dr_support/services/prism_preview_runtime.py), [profile validator](dr_support/services/deployment_profile.py), [recovery source](dr_support/persistence/recovery.py) | Selective read-only corroboration: missing ordinary binding, pure endpoint checks และ guard refusal; source presence ไม่ใช่ runtime PASS |

### 20.2 Private retained evidence นอก repository

ฐาน `ARTIFACT_ROOT = C:\Users\User\Documents\Codex\2026-10-21\task` Paths ด้านล่าง relative ต่อฐานนี้ ไม่ต้องย้าย artifacts/images/DB/weights/private files เข้า Git หรือ software release เพื่อให้ links portable

| Ref/path | ผลที่ตรวจจาก retained file / integrity anchor |
| --- | --- |
| `CLI_TO_PEPO_GPT_DOT_HANDOFF_20261023.md` | External handoff ที่ owner ระบุ; historical source/ownership/evidence context ใหม่กว่าบางข้ออยู่ E-02 |
| `demo-evidence-session04-20261023/FINAL_STATUS.json` | Re-read aggregate status/counts/browser/clinical/T4 boundaries; SHA256 `fb803f4d7f7c1535bcb665792523de2ad61a703ee02652976a95ed7a168bef88` |
| `demo-evidence-session04-20261023/EXPORT_VERIFICATION.json` | Re-read saved467/source240/no source or clinical-state changes/zero physician labels; SHA256 `ee974cb10cd1bd79e6ba843125127caebb37c3a2c7f5a48d794bf863a4bbb00d` |
| `demo-evidence-session04-20261023/PRISM_POSTFILTER_MEASUREMENT.json` | Re-read actual230/raw65,639/proposed8/UI3/zero new model calls/clinical NOT_MEASURED; SHA256 `ea2a6485254caf5528fa80150ffe23a6840d88bd659a403330c92b838f641df7` |
| `demo-evidence-session04-20261023/SUPPRESSION_AUDIT.json` | File/hash inspected; historical undo7 อ้างตาม HANDOFF ไม่ใช่ rerun ใน GOAL; SHA256 `ee6c4f2c3c2a6c5eeffe14b00b1131481114395f1af85e6944c2abf213f28eb3` |
| `demo-batch-evidence-20261022-b03/accounting/LEDGER.jsonl` | File hash และ1,423 rows ตรวจตรง anchor; SHA256 `ebc4f23ac5b9d89f136ada7a36b08350ddacf186e338a50c0ea5ba6f5ba14d98` ไม่สร้าง/แก้ ledger |
| `m1-context-qualification-20261023-01/CONTEXT_QUALIFICATION.json` | Re-read APP_CONTEXT_PASS, actual runtime/migration/raw readback PASS, SYNTHETIC/zero RPC/inference; SHA256 `2d42b254dbb210bc4c81cbe9687af86a50b4b27281d92bf237f0c3a9c5d3df71` |
| `hospital-m1-recovery-qualification-20261023-01/QUALIFICATION.json` | Re-read PARTIAL, backup/restore/readback PASS, export BLOCKED409; SHA256 `a930ea2c34ea3ad2cd7d29f6d0689ec91f1487a9125756d54634c4debf1dec3c` |
| `hospital-qa-spec-draft-20261023/MEASURED_BASELINE.json` | File/hash metadata inspected; resource/latency aggregates ใน GOAL อ้างผ่าน HANDOFF/sizing draft; SHA256 `f6b0f6f2bcb4c77e71e2f55e9430cc35340b6df350b5742b49b98656f57667ec` |
| `M1_ACL_READONLY_FINDINGS_20261023.md` | Read report ของ old Windows four allows และ separate historical Linux metadata; ไม่อ่าน secret contents/ไม่แก้ permissions |

สำหรับการตรวจรอบถัดไป ให้เริ่มจาก status matrix และ milestone ที่ยังเปิดอยู่ ยืนยันเฉพาะ facts/bytes/สิทธิ์ที่จำเป็นกับ action นั้น แล้วต่อยอดของเดิมจนส่งมอบสอง profiles ได้ครบ
