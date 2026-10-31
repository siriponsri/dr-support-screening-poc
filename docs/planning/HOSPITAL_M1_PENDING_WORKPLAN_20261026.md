# Hospital M1: งานค้าง แยกเดินต่อได้กับรออนุมัติ (26 ต.ค. 2569)

สถานะ: เอกสารเตรียมงาน / จัดทำโดย Claude Code / TEST_ONLY ทั้งหมด ไม่ใช่การตรวจรับที่โรงพยาบาล
ไม่มีการ reboot, หยุดบริการทีม, เปิด GPU session ใหม่ หรือใช้โควตาในรอบนี้

## 1. ยอดโควตาจาก ledger (อ่านอย่างเดียว 26 ต.ค. 2569)

อ่านจาก `ACCOUNTING.json`, `LEDGER.jsonl` และ `windows/*/BUDGET.json` ของ 3 decision บน dr-train
ไม่มีการ reset และยอดคงเหลือใช้ไม่ได้จนกว่าจะมี decision ใหม่ที่ owner อนุมัติ

**Requests (นับสะสมของ M1)**

| Decision | ใช้แล้ว | เพดาน | คงเหลือใน decision | อายุการอนุมัติ |
| --- | --- | --- | --- | --- |
| `HOSPITAL_M1_ACCOUNTING_20261023` | 531 (525 + 6) | 549 | ปิดแล้ว (fence 24 ต.ค.) | ใช้ครั้งเดียว; window Server ปิด 23 ต.ค. |
| `HOSPITAL_M1_ACCOUNTING_PRISM_20261024` | 534 (531 + 3) | 534 | 0 / fence 25 ต.ค. | ใช้ครั้งเดียว; window ปิด 24 ต.ค. |
| `HOSPITAL_M1_ACCOUNTING_SERVICE_20261025` | 540 (534 + 6) | 540 | 0 / ยังไม่ fence | ใช้ครั้งเดียว; ทั้งสอง window ปิด 25 ต.ค. |
| **รวม M1** | **540** | **549** | **9** (QA_LOCAL 6, post-fix 3 ที่ยังไม่ส่ง) | ไม่มีวันหมดอายุบันทึกไว้ แต่ใช้ได้เฉพาะผ่าน decision ใหม่ที่อนุมัติ |

**GPU seconds (การจองใหม่ของ M1, คิดเต็ม lease แบบ conservative)**

| Window | จอง/คิดแล้ว | เพดาน window | เริ่ม (UTC) | สถานะ |
| --- | --- | --- | --- | --- |
| `HOSPITAL_M1_QA_SERVER_20261023` | 10,800 | 10,800 | 2026-10-23 12:35 | ปิด, ไม่ quarantine |
| `HOSPITAL_M1_QA_SERVER_PRISM_20261024` | 3,600 | 3,600 | 2026-10-24 05:42 | ปิด |
| `HOSPITAL_M1_QA_SERVER_WATCHDOG_20261025` | 900 | 900 | 2026-10-25 13:14 | ปิด |
| `HOSPITAL_M1_QA_SERVER_SERVICE_20261025` | 3,600 | 3,600 | 2026-10-25 13:19 | ปิด |
| **รวมใหม่** | **18,900** | **21,600** (อนุมัติ 23 ต.ค.) | | **คงเหลือ 2,700** |

ยอดก่อน M1 ที่เก็บไว้ (ไม่นับในงบใหม่): 17,002.874 วินาที / ทุก window เป็น lease เดียว
ไม่ต่ออายุ ไม่คืนเวลา / ไม่มี window ใดเปิดอยู่

## 2. รายการที่เดินต่อได้เลย (ไม่ต้องรออนุมัติ)

| รายการ | ทำแล้วในรอบนี้ | ยังเหลือ |
| --- | --- | --- |
| AC-12 | ปรับตาราง GOAL ตามหลักฐาน phase A | หลักฐานบริการจริงยังไม่มี |
| Watchdog | บันทึกสาเหตุ error แบบ allowlist + tests | ยังไม่ deploy ไปเครื่อง GPU (deploy ใหม่ต้องผูกกับ decision ใหม่) |
| AC-09 | `scripts/qa/check_export_folder.py` + tests บน synthetic export | export จริงรอปลายทางที่อนุมัติ |
| AC-11 | `tests/test_m1_fault_injection.py` + gap analysis | การแก้ข้อความ G1–G5 รออนุมัติ |
| AC-01 / AC-17 / MS-09 | ภาพหน้าจอจากข้อมูล synthetic/public 10 ภาพ | installation candidate (ยังไม่สร้าง), ทดสอบติดตั้งบนเครื่องสะอาด, PDF |

## 3. AC-08: checklist ก่อนและหลัง reboot (owner เป็นผู้ reboot เอง)

ระบบจะไม่ reboot เครื่องเอง ใช้ workspace TEST_ONLY `windows-demo-test-only`
และเคสเดิมจากการทดสอบ restart (`07bc59b8…`) ไฟล์หลักฐานเก็บใน `M1PrivateConfig\evidence\` เท่านั้น

**ก่อน reboot**

1. เปิดแอปตามปกติ (`START_DR_SCREENING.bat`) ตรวจว่า `http://127.0.0.1:8000/health` ตอบ 200
2. บันทึก snapshot ของเคสทดสอบ:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.qa.m1_local_acceptance snapshot --workspace-id windows-demo-test-only --case-id 07bc59b885de06bdd0260c771aabde195c26125e824269a691eb566a61a5cd19 --label ac08-before-reboot --out <private evidence folder>
   ```

3. จดจำนวนเคสใน Worklist และเกรดของเคสทดสอบ (ดูจากหน้าจอ ไม่ต้องคัดลอกชื่อผู้ป่วย)
4. ปิดแอปด้วย `STOP_DR_SCREENING.bat` และปิดโปรแกรมอื่นตามปกติ แล้วจึง reboot

**หลัง reboot**

1. เปิด Docker Desktop ถ้ายังไม่เปิดเอง แล้วเปิดแอปด้วย `START_DR_SCREENING.bat`
2. ตรวจ `/health` = 200 และข้อความ launcher "least-privilege runtime role"
3. บันทึก snapshot ใหม่ (`--label ac08-after-reboot`) แล้วเทียบ:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.qa.m1_local_acceptance compare <before.json> <after.json>
   ```

4. **ผ่านเมื่อ** ทุก field เท่ากัน, `annotation_set_hash_matches` = true, จำนวนเคสและเกรดตรงกับที่จดไว้,
   เปิดภาพต้นฉบับได้, และ `pg_stat_activity` ยังแสดงแอปเป็น `dr_support_runtime`
5. **ไม่ผ่าน** ถ้า field ใดเปลี่ยน, แอปเริ่มไม่ได้ หรือ DB เปลี่ยนกลับเป็น SQLite: หยุด ไม่แก้ข้อมูล แล้วรายงาน

## 4. AC-09: export

- ตรวจรูปแบบได้แล้วด้วยข้อมูล synthetic (`tests/test_export_folder_check.py`)
- export จริง: owner เลือกโฟลเดอร์ local ปลายทางที่อนุมัติเอง (ห้ามเป็น network share, mapped drive
  หรือโฟลเดอร์ sync cloud ซึ่งแอปปฏิเสธอยู่แล้ว) แล้วรันตรวจแบบอ่านอย่างเดียว:

  ```powershell
  .\.venv\Scripts\python.exe -m scripts.qa.check_export_folder <dataset-export-folder>
  ```

  เครื่องมือพิมพ์เฉพาะจำนวนและชื่อการตรวจ ไม่พิมพ์ข้อมูลรายแถว
- ผมจะไม่เลือกปลายทางแทน owner

## 5. AC-15 / MS-08: ข้อมูลและการอนุมัติที่ต้องขอจาก IT

ยังไม่ใช้ข้อมูลผู้ป่วยเพิ่ม และไม่ถือว่าได้รับอนุมัติจนกว่าจะมีหนังสือหรือข้อความยืนยันจากผู้มีอำนาจ

| # | สิ่งที่ต้องขอ | ใช้กับ |
| --- | --- | --- |
| 1 | ผู้อนุมัติข้อมูล (data owner) และขอบเขต: ภาพประเภทใด, ช่วงเวลา, จำนวน, วัตถุประสงค์ research-only | AC-15 |
| 2 | เส้นทางข้อมูลที่อนุญาต: โฟลเดอร์ต้นทาง (อ่านอย่างเดียว), ห้าม browse storage ของโรงพยาบาล, ห้ามส่งออกนอกเครือข่าย | AC-15 |
| 3 | สิทธิ์ Windows ของบัญชีที่รันแอป (SID กลุ่มอ่านอย่างเดียว) และนโยบาย antivirus/backup ของโฟลเดอร์ | AC-15, MS-08 |
| 4 | เครื่องเป้าหมาย QA_LOCAL: รุ่น, CPU/RAM/ดิสก์, GPU และ driver, Windows version, สิทธิ์ admin สำหรับติดตั้ง | MS-08 |
| 5 | Docker Desktop หรือ PostgreSQL ที่อนุญาต, พอร์ตที่เปิดได้ (loopback เท่านั้น) | MS-08 |
| 6 | ที่เก็บ model assets และวิธีตรวจ checksum บนเครื่องเป้าหมาย (ไม่มีอินเทอร์เน็ตหรือมี) | MS-08 |
| 7 | ปลายทาง export ที่อนุมัติ และผู้รับผิดชอบ | AC-09 |
| 8 | ปลายทาง backup ที่อนุมัติ, ระยะเก็บ, การเข้ารหัส | AC-13, MS-07 |
| 9 | ช่วงเวลาที่อนุญาตให้ reboot และทดสอบ cold start | AC-08, MS-08 |
| 10 | ผู้ติดต่อ IT เมื่อเกิดเหตุ และขั้นตอนแจ้งเหตุข้อมูล | ทุกข้อ |

## 6. AC-14 / MS-05: แผนทดสอบ (เตรียมเท่านั้น ยังไม่รัน)

**AC-14 หยุด / สถานะ / เริ่มใหม่ ไม่กระทบงานทีม**: หลักฐานจาก bounded session มีแล้ว (GPU1/Ollama ไม่ถูกแตะ)
แผนสำหรับบริการตัวจริงเมื่อได้รับอนุมัติ:

1. บันทึก GPU1 compute PIDs, Ollama PIDs และ Docker volumes ของทีมก่อนเริ่ม
2. start, status, stop, start ซ้ำ โดยตรวจทุกครั้งว่า PID เดิมของทีมยังอยู่และ volume ไม่เปลี่ยน
3. ตรวจว่า stop คืน GPU0 และไม่มี listener 0.0.0.0
4. เกณฑ์ผ่าน: ไม่มี process ของทีมหายไป, ไม่มี volume ถูกแตะ, cleanup CONFIRMED ทุกครั้ง

**MS-05 QA Server ordinary-main E2E**: ขั้นตอนต่อจาก MS-03 (ใช้หน้าแอปปกติ)

1. ต้องมีก่อน: decision ใหม่ที่ owner อนุมัติ (จำนวน request, GPU seconds, window), deploy ที่ตรวจ identity แล้ว
2. AC-03 ถึง AC-12 ตามลำดับเดียวกับ runbook: Confirm Image, วิเคราะห์ USPEC/RETFound/PRISM,
   readback ทุกครั้ง, แพทย์ทดสอบแก้เกรด/กล่อง, reopen, restart, export (ปลายทางที่อนุมัติ)
3. ไม่มี retry อัตโนมัติ; ล้มเหลวหรือไม่แน่ชัดให้หยุดและปิด session
4. ใช้โควตาเหลือ 9 request และ 2,700 GPU seconds ได้ไม่เกินนี้ และเฉพาะหลังอนุมัติ
5. ประเด็น mask ทางคลินิก (AC-10/MS-06) **ไม่ปิดกั้น** E2E ทางเทคนิค: E2E ใช้ค่า default ปัจจุบัน
   (ไม่มี external mask, artifact post-filter ปิด) และบันทึกว่าไม่ใช่การยอมรับ mask ทางคลินิก

## 7. รายการรออนุมัติ / รอการตัดสินใจ

| รายการ | ต้องการ |
| --- | --- |
| AC-08 reboot | owner reboot เครื่องเองตาม checklist ข้อ 3 |
| AC-09 export จริง | owner เลือกปลายทางที่อนุมัติ |
| AC-10 / MS-06 | owner เลือกวิธี mask (ดู `HOSPITAL_M1_MASK_OPTIONS_20261026.md`) |
| AC-11 G1–G5 | owner อนุมัติการแก้ข้อความและ error class (ดู gap analysis) |
| MS-07 RC-03 | owner และ DB/IT เลือกแนวทาง guard-aware recovery |
| AC-15 / MS-08 | ข้อมูลและการอนุมัติจาก IT ตามข้อ 5 |
| AC-14 / MS-05 | decision โควตาใหม่ และช่วงเวลาที่ไม่กระทบทีม |
| Final release | ตรวจ installation candidate บนเครื่องสะอาดครบก่อนติดป้าย final |
