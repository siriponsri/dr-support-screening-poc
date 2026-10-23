# Focused launcher fix handoff — Pepo → Claude

23 ตุลาคม 2026 · ขอบเขต: diagnostic, endpoint/token-source pairing, explicit credential-transfer opt-in และความหมายของ bounded acceptance runner

Owner ยืนยันว่าหยุด Claude แล้วและให้ Pepo แก้เฉพาะประเด็นที่รีวิว พร้อมทดสอบ local CPU และส่ง prompt กลับ งานนี้ไม่ใช่การเปิด audit หรือออกแบบ Hospital M1 ใหม่

## Source และสิ่งที่รักษาไว้

- Worktree: `C:\Users\User\Documents\Codex\2026-10-21\task\m1-model-host-session-worktree`
- Branch: `feat/m1-model-host-session`
- HEAD ก่อน/หลัง focused pass: `8d809e4fc502dfa62a8cc3e9fb86d353d4c3c577` เริ่มจาก status สะอาด
- รักษา commits `5ec2570`, `eac5d29`, `2c37171` และ `8d809e4` ไม่ checkout/reset/merge/push หรือแก้ history
- Main เป็น `4ddb6a3` ตอนเริ่มงาน มี owner changes ใน root `HANDOFF.md` และ owner untracked เดิม จึงไม่แก้ root HANDOFF/GOAL/CLAUDE หรือดูดงานเหล่านั้นเข้าการส่งมอบนี้
- ส่งเป็น reviewed working-tree diff และไฟล์ใหม่สองไฟล์ ให้ Claude รับต่อภายใต้ branch เดิม ยังไม่ commit/push และยังไม่ใช่ integrated Hospital M1 release

## เปลี่ยนอะไร

| File | การเปลี่ยน |
| --- | --- |
| `scripts/qa/m1_server_app.py` | เพิ่ม `diagnose`; รวม fixed model selection ใน `model_configuration()` ให้ diagnostic, environment และ composition ใช้ logic เดียวกัน; `serve` และ direct `host_token()` ต้อง explicit boolean opt-in ก่อนทำ action |
| `scripts/model-server/m1_session.py` | แก้ module description ให้ชัดว่าเป็น bounded acceptance runner ไม่ใช่ installed persistent hospital service; ไม่มีการเปลี่ยน budget/lease/lifetime/watchdog |
| `tests/test_m1_server_app_config.py` | Regression tests ของ redaction, no-side-effects, source/endpoint selection, environment restoration และ opt-in refusal ก่อน SSH/config/probes/app |
| `docs/operations/M1_LAUNCHER_FIX_HANDOFF_20261023.md` | Handoff และ prompt ฉบับนี้ |

ไม่แก้ model/checkpoint/threshold, source/export policy, DB schema, actual environment/credentials, ACL, services หรือ request accounting

## ตรวจ config โดยไม่เปิดเผย secret

จาก feature worktree เดิม ใช้ interpreter เดียวกับที่ตั้งใจใช้รัน launcher:

```powershell
rtk proxy C:\Users\User\Desktop\myProject\dr-support-screening-poc\.venv\Scripts\python.exe -B -m scripts.qa.m1_server_app diagnose
```

คำสั่งนี้รันจริงหนึ่งครั้งใน focused pass และได้ `CONFIGURATION_SELECTED_NOT_VALIDATED`:

- Python: canonical project `.venv\Scripts\python.exe`; cwd: feature worktree ข้างต้น
- Profile: `QA_SERVER`, app `review`, model runtime `remote`
- Selected endpoint: scheme `http`, host `127.0.0.1`, port `47860` โดย default หรือ `--model-port` ที่ระบุ
- Tunnel target ที่เลือก: existing SSH host `siripon@100.77.149.83`, remote loopback `127.0.0.1:7860`
- Token source ที่เลือก: `/home/siripon/projects/dr-model-api-qa/config/private/model-api.env`
- `source_selected=true`, `source_presence=NOT_CHECKED`, `value_loaded=false`, `authentication=NOT_CHECKED`, `transfer_opt_in=false`
- Database configuration `NOT_READ`; ไม่มีการอ่าน private files, SSH, socket probe, app/model/GPU startup, lease reservation หรือ data mutation

Diagnostic แสดงการเลือกของ process ที่เรียกคำสั่งนี้ ไม่ได้ inspect environment ของ app process เก่าที่เปิดอยู่ และไม่ได้พิสูจน์ listener, source-file existence, token validity หรือ authentication แม้เรียก `diagnose --allow-remote-token-read` ก็ไม่อ่าน token เพียงแสดง opt-in ที่ส่งมา

สำหรับ launcher นี้ repository `.env` และ inherited `REMOTE_MODEL_*` ไม่ใช่ source ที่เลือก `session_environment()` เคลียร์ config กลุ่มที่เกี่ยวข้อง โหลด private DB configuration เดิม แล้วกำหนด endpoint และ token ที่ส่งให้ composition ดังนั้น token ของ Windows `.env` ต่างจาก token ของอีก endpoint/session ไม่ได้แปลว่า launcher นี้เสีย อย่าแก้ `.env`, เปรียบเทียบ secret hashes หรือคัดลอก token เพื่อทำให้ตรงโดยไม่มีเหตุผลเรื่อง paired endpoint/source

แหล่ง DB ของ `workspace`/`readback`/`serve` ยังคงเป็น `M1PrivateConfig\m1_runtime.env` และ authority ใช้ `m1_authority.env` ตาม privacy/role checks เดิม Diagnostic ไม่เปิดไฟล์เหล่านี้

## Credential-transfer decision ที่ยังต้องแยกจากงานโค้ด

`serve` เดิมเรียก `host_token()` อัตโนมัติ ตอนนี้ค่าเริ่มต้นปฏิเสธด้วย `REMOTE_TOKEN_READ_REQUIRES_EXPLICIT_OPT_IN` ก่อนอ่าน pins/config, probe, SSH, tunnel หรือ app construction ส่วน `workspace` และ `readback` เดิมไม่ถูกเพิ่ม gate นี้

หากต้องใช้เส้นทางนี้ ให้ owner อนุญาต action ที่ตรงกัน:

> อ่าน token เดิมจาก `/home/siripon/projects/dr-model-api-qa/config/private/model-api.env` ผ่าน existing verified SSH identity `siripon@100.77.149.83` เข้า memory ของ Windows launcher process นี้ เพื่อใช้กับ owned loopback tunnel ไป model session `127.0.0.1:7860` โดยไม่พิมพ์/log/เขียน token ลงไฟล์ ไม่เปลี่ยน credentials หรือ ACL

หลังมีการอนุญาตตรง action นี้แล้วจึงใช้ `serve --allow-remote-token-read ...` Flag เป็น opt-in ไม่ใช่หลักฐานว่า owner อนุมัติหรือว่า authentication ผ่าน ห้ามเปิด flag แทนคำอนุมัติ และไม่ต้องขออนุมัติซ้ำหากมีหลักฐานอนุญาต action เดิมครบแล้ว

**Focused pass นี้ไม่ได้อ่าน/ดึง token หรือเปิด SSH** การตัดสินใจนี้ไม่ขวาง independent source/package/mask/recovery work และไม่ใช่ gate ใหม่สำหรับ routine engineering ทุกขั้น

## Validation ที่ทำจริง

รันจาก feature worktree ด้วย canonical project Python โดยตั้ง `PYTHONDONTWRITEBYTECODE=1` และ `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` สำหรับ pytest:

```powershell
rtk proxy C:\Users\User\Desktop\myProject\dr-support-screening-poc\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_m1_server_app_config.py tests/test_m1_session.py
```

ผล: **54 passed in 9.74s** ใช้ synthetic values/fake SSH/fake app/child และ temporary test files ไม่มี actual credential/network/model API/GPU/DB connection

```powershell
rtk proxy C:\Users\User\Desktop\myProject\dr-support-screening-poc\.venv\Scripts\python.exe -m ruff check scripts/qa/m1_server_app.py scripts/model-server/m1_session.py tests/test_m1_server_app_config.py
```

ผล: **All checks passed** และ tracked source `git diff --check` ผ่านก่อนเพิ่มเอกสารนี้ ตรวจ scoped diff แล้วมีเพียง source changes ข้างต้นและ synthetic tests ไม่มี actual secret values/secret hashes/DSNs จากเครื่องจริง

**NOT_RUN:** full backend/frontend suite, actual SSH/token retrieval/authentication, tunnel/listener, real DB/workspace composition/readback, actual inference/GPU activation, hospital target/offline/reboot, package install และ clinical evaluation ไม่ใช่ความล้มเหลวของ focused tests และไม่ได้ถูกนับเป็น PASS

## Persistent service ที่ Claude ยังต้องทำต่อ

Acceptance runner ปัจจุบันมี session limit 2640s, child hard cap 2730s และ existing single-window/one-lease controls การปิด session ไม่ใช่เส้นทาง restart ของ installed hospital service ห้ามทำให้ดู persistent ด้วยการลบหรือยืด budget limits เอง

งานต่อที่ตรง GOAL `MS-03`, `OP-01–09`, `AC-02,08,11,12,14`:

1. ต่อ installed start/status/stop เข้ากับ existing owned process/service lifecycle ให้พร้อมตลอดช่วงแพทย์ที่ตกลงไว้ แยก asset/load/protocol/inference/queue/DB states
2. ปิด ordinary app/service integration และพิสูจน์ actual startup/SQL/reopen บน approved test context; bounded acceptance runner ใช้เก็บหลักฐานตามงบได้ แต่ไม่แทน installed service
3. กำหนดและทดสอบ restart/reboot recovery ของ app/PG/model service โดยรักษา history, labels, durable request accounting และ old-job quarantine ไม่มี sent/uncertain replay หรือ epoch/TTL unlock
4. ให้ bounded queue/deadlines/watchdog/drain และ ownership ไม่กระทบ workloads อื่น พร้อม procedure เมื่อ reservation/session หมด โดยไม่ auto-renew หรือรีเซ็ตประวัติ
5. ติดตั้ง service/autostart ที่ต้อง privileges เฉพาะเมื่อมี IT/owner authorization ตรง action เก็บ actual target evidence แยกจาก source/fake tests

ข้อ 1–5 เป็น implementation/acceptance ที่เหลือ ไม่ใช่การขอให้เริ่ม audit ใหม่ หรือรอรีวิว Pepo รอบถัดไปก่อนทำทุกไฟล์

## Prompt ให้ Claude กลับมาทำ GOAL ต่อ

```text
Claude กลับมารับหน้าที่ sole application-code writer ได้แล้ว Pepo จบ focused fix pass และหยุดเขียนแล้ว

เริ่มที่ worktree C:\Users\User\Documents\Codex\2026-10-21\task\m1-model-host-session-worktree
branch feat/m1-model-host-session, HEAD ที่ส่งต่อ 8d809e4fc502dfa62a8cc3e9fb86d353d4c3c577
มี reviewed diff สอง source files และไฟล์ tests/เอกสารใหม่ตาม docs/operations/M1_LAUNCHER_FIX_HANDOFF_20261023.md
ตรวจ HEAD/status/preimage ก่อนรับ diff ห้าม reset/stash/checkout ทับงานหรือดูด owner untracked เข้า commit
คง commits 5ec2570/eac5d29/2c37171/8d809e4 และ main/HANDOFF/GOAL ของ owner ตามจริง

อ่าน focused handoff นี้กับ GOAL และ HANDOFF addendum ล่าสุด แล้วลงมือทำงานที่เหลือ ไม่เริ่ม broad audit หรือออกแบบ scope ใหม่
Focused pytest ของ launcher/session ผ่าน 54 tests, Ruff ผ่านแล้ว ไม่ต้องรันซ้ำทั้งหมดถ้ายังไม่มี changes/failure ที่เกี่ยวข้อง
รับ diff และ commit ตาม project instructions เมื่อพร้อม; การส่งต่อนี้ยังไม่ได้ merge/push หรือรับรอง full release

ทำ MS-03/MS-04 ให้ใช้งานได้ก่อน live acceptance: ordinary integration, owned lifecycle/native admission/result/readback, exact approved operation manifest และ durable accounting
ใช้ diagnose เพื่อดู Python/cwd/paired endpoint/source แบบไม่อ่าน secrets ค่า NOT_CHECKED ไม่ใช่ authentication PASS
serve ต้องมี --allow-remote-token-read เฉพาะเมื่อ owner อนุญาตการอ่าน server token ผ่าน SSH เข้า Windows process memory ตรง action แล้ว ถ้ายังไม่มี ให้ถามเฉพาะ action นี้และทำงานอิสระต่อ ห้ามแก้ token/.env/ACL หรือใช้ flag แทน approval

Bounded runner ไม่ใช่ persistent hospital service ต่อ no-code start/status/stop และ restart/reboot recovery ตาม GOAL โดยคง request/lease/time limits และ no-replay semantics ห้ามตัด limits เพื่อให้ดูพร้อมใช้งาน
จากนั้นปิด MS-05–09/acceptance ที่เกี่ยวข้องให้ครบสอง profiles ไม่จบที่ one-shot demo:
- QA Server: actual USPEC UWF, RETFound CFP, protected PRISM ผ่าน ordinary UI → SQL → review/edit/save/reopen/export; failure/recovery และ target route/data boundaries
- QA Local: app/PG/images/weights/inference อยู่ hospital target และ normal operation offline; หากยังไม่มี target ให้คง NOT_RUN ของ onsite checks และเตรียม package/source ต่อ
- Mask ยังเป็น M1: actual stage/input visibility, reversible suppression/raw/uncertain/undo, retained-result comparison และ human adjudication ทั้ง false ROI/true-lesion loss ไม่บังคับ approve mask เพิ่มทุกภาพหรือข้าม protected preview
- Physician labeling/export/provenance/test-data isolation, PostgreSQL migration/roles/audit, guard-aware backup/restore/rollback และ authorized hospital export ตาม owner decisions ล่าสุด ห้าม auto-gold หรือถอด source/security gates
- Final versioned package, secret-free templates สอง profiles, install/maintenance guide, actual E2E evidence/screenshots/timing, gallery/HTML และ operator walkthrough

ก่อน GPU ใช้ ให้ตรวจ current durable ledger และ approvals จริง เก็บ historical525/cap549 และ scope24ตามเอกสารโดยไม่สมมติยอด live ใช้ Server ไม่เกิน9เฉพาะเมื่อ MS-01–04 พร้อม/operation list-hashได้รับอนุมัติ/รายงานก่อนเปิดตาม owner instruction
ไม่มี automatic retries/renewal/terminal-job replay ใช้ approved GPU0 เท่านั้น ไม่แตะ GPU1/V100/Ollama/paid services หรือ workloads อื่น

ทำ focused fixes/tests ตาม defect และ required integration checks ณ จุดส่งมอบ ไม่วน audit เต็มซ้ำหรือเพิ่ม review phases ทุกขั้น
อย่าถาม owner เรื่อง routine reversible engineering ที่อยู่ในสิทธิ์แล้ว ถ้ามี actual security denial, missing action-specific permission หรือ frozen clinical/schema conflict ให้หยุดเฉพาะ action นั้น รายงาน exact target/reason/outcome แล้วทำ independent authorized work ต่อ
อัปเดต facts/evidence/status ตามผลจริง แยก source/fixture/actual runtime/physician/clinical outcomes ไม่อ้าง DONE จาก health/load/test counts
รายงานผลที่ใช้ได้จริงกับ next smallest action อย่างสม่ำเสมอ ไม่ต้องรอ Pepo review รอบใหม่เป็นเงื่อนไขทำงานที่อนุญาตแล้ว
```
