# Web deployment review handoff

สถานะ: เป็นแผนตรวจรับและ template สำหรับทีม ยังไม่ได้ deploy หรือรับรองความพร้อมของ QA Cloud/เครื่องโรงพยาบาล

## รูปแบบที่เสนอ

ให้เครื่อง Review ใช้ `APP_PROFILE=review`, `MODEL_RUNTIME=remote`, `DR_SUPPORT_CASE_STORE=postgres`, `WORKERS=1` ต่อไป เครื่องนี้ไม่ต้องมี GPU หรือ model weights ส่วน Model API แยกเป็นบริการของทีมเจ้าของเดิม ใช้ capability discovery ระบุ task/modality/readiness ก่อนเปิดปุ่ม AI หากไม่มี Model API ก็ทำ manual review ได้ แต่ PostgreSQL ที่เป็นแหล่งบันทึกหลักยังต้องพร้อม

เครื่องโรงพยาบาลใช้ launcher ที่มีอยู่จาก release package: FIRST_RUN ครั้งแรก แล้ว START / CHECK_SYSTEM / STOP ในงานประจำ ผู้ใช้ไม่ต้องเรียก npm หรือจัดการ dependency เอง QA Cloud ควรใช้ app artifact เดียวกันหลัง reverse proxy ที่ทีมอนุมัติไว้ ไม่เปิดบริการใหม่จาก audit checkout นี้

`deployment-review-plan.json` ระบุ review profiles ทั้งสองแบบ ไม่มี URL จริง รหัสผ่าน token หรือ path ผู้ป่วย ตรวจโครงสร้างแบบ offline ได้ด้วย:

```powershell
python scripts/audit/validate_web_deployment_plan.py docs/audit/deployment-review-plan.json
```

คำว่า PLAN STRUCTURE VALID หมายถึงผ่านข้อกำหนดในไฟล์เท่านั้น ยังไม่ใช่ service readiness และไม่ยืนยันว่า backup/restore หรือ cloud ingress ใช้งานได้จริง

## ก่อนทำ release

1. ระบุ commit ที่ผ่าน review และตรวจ preimage ทุกไฟล์ก่อนรวม patch อย่าใช้ snapshot นี้แทน canonical ทั้งโฟลเดอร์
2. ใช้ lockfiles เดิม สร้าง dependency cache/wheelhouse กับ frontend artifact ในขั้น build ที่ได้รับอนุญาต บันทึกเวอร์ชัน Python/Node, lockfile hashes และผลตรวจทดสอบ ไม่ติดตั้งหรือดาวน์โหลด dependency ระหว่าง START ประจำวัน
3. ตรวจ `frontend/dist/build-identity.json` ให้ source digest และ output-set hash ตรงกับ release ที่จะส่ง เก็บ artifact ก่อนหน้าไว้สำหรับ rollback
4. ตรวจ config จากชื่อ key/ค่าไม่ลับที่จำเป็นเท่านั้น เก็บ database URL, remote token และค่าจริงในระบบของ operator ห้าม dump .env หรือส่ง secret ไป browser/log ไม่มีการเปลี่ยน credential ใน audit นี้
5. ติดตั้ง read-only source mounts และ read-only verified weights mounts แยกตามเจ้าของข้อมูลและ Model API ส่วน PostgreSQL/output/state ต้องแยก writable volume อย่านำ model weights มารวม app image
6. ใช้ Compose PostgreSQL template เดิม `deployment/docker-compose.local-postgres.yml` ใน release ที่ผ่านตรวจแล้ว ตรวจ healthcheck และการเชื่อมต่อ SELECT 1 ผ่าน credential-safe diagnostic ภายใต้สิทธิ์ operator ห้ามใช้ database ทดสอบของงาน Model API เป็นเป้าหมาย
7. ก่อน cutover ให้สำรอง PostgreSQL, workspace metadata, release identity และ export ที่อนุมัติ เก็บนอก repo พร้อมนโยบายเข้าถึงและ retention ของโรงพยาบาล ทดสอบ restore ลงปลายทางแยกที่อนุมัติไว้และตรวจ case counts/revisions/hashes ก่อนเขียนคู่มือว่า restore ผ่านแล้ว
8. หากมี migration ใน release อื่น ต้องมีแผน forward/rollback ตาม schema version และจุดหยุด writer ที่ชัดเจน งานนี้ไม่มี migration อย่าคืนฐานข้อมูลเก่าทับ clinical writes ที่เกิดภายหลัง
9. smoke ด้วย synthetic manual flow ตรวจเปิด workspace, queue, original image, save/reload, switch case, offline AI และ rejected stale revision ห้ามนำ smoke inference ไปปนกับ audit ที่ไม่อนุญาต inference

## START / STOP และ readiness ที่ยังต้องปรับ

Launcher เดิมแยก PID/checkout และ Compose project ไว้แล้ว แต่ process guard ยังเทียบ PID กับ command/path เป็นหลัก ควรเพิ่ม OS process creation time และ checkout identity ก่อนหยุด process เพื่อกัน PID ถูกนำกลับมาใช้ใหม่ ต้องมี synthetic fixture tests ก่อนแก้และไม่ทดสอบด้วยการหยุด process ของทีมอื่น

`/health` ที่ตอบ HTTP 200 อย่างเดียวไม่พอ ควรแยก app alive, PostgreSQL ready, frontend identity ready และ model/manual mode บน diagnostic ที่อ่านง่าย งานนี้ปรับความซื่อตรงของ health pill ฝั่งหน้าเว็บแล้ว ส่วน launcher semantic health และ readiness ครบชุดยังเป็นงานค้าง

## เมื่อระบบขัดข้อง

ถ้า AI offline แต่ app/ฐานข้อมูลพร้อม ให้แสดง manual review และเก็บการยืนยันของแพทย์ตามเดิม ถ้าบันทึกไม่สำเร็จ ให้คง draft และเคสเดิมพร้อมวิธีกู้คืน ถ้า queue โหลดไม่สำเร็จ อย่าประกาศว่าตรวจครบแล้ว

เก็บ telemetry เฉพาะ request ID, route แบบไม่ใส่ patient ID, HTTP status, latency bucket, release identity และ error category ห้ามบันทึก image bytes, DICOM headers, patient identifiers, database URL หรือ token เก็บเหตุการณ์ clinical audit ในกลไก revision/history เดิม ไม่ใช้ browser log แทน audit trail

รอบ qualification ถัดไปให้ทีมเลือก QA release ที่แน่นอน ทดสอบ start/stop/restart, backup/restore และ manual 10-case flow แล้วแนบ receipt แยกจากผล frontend fixture tests ของ audit นี้


## Review service template และ health/readiness

เพิ่ม `review.compose.template.json` ซึ่งเป็น Compose JSON template สำหรับทีมตรวจต่อ ใช้ app image เดียวของ release ที่อนุมัติและระบุด้วย `@sha256:<digest>` เท่านั้น ไม่มี build/pull command ใน audit นี้ template ไม่มี Model API หรือ PostgreSQL service เพิ่ม จึงไม่สร้างบริการแข่งกับทีมเดิม หากใช้ Docker ให้ operator เตรียม state/output volumes แยกไว้ก่อน ส่วนเครื่องโรงพยาบาลที่ใช้ Windows launcher เดิมไม่ต้องเปลี่ยนไปใช้ Docker app เพื่อใช้แพตช์นี้

ด้านนอก container bind เฉพาะ loopback ด้านใน `HOST=0.0.0.0` เพื่อรับ port mapping ของ container การเปิด ingress/reverse proxy/TLS เป็นงาน operator ที่ต้องตรวจตามนโยบายเดิม ไม่มีการเปลี่ยน network/security configuration ใน audit นี้

Mounts แยกเป็น source `/data/source` แบบ read-only, state `/app/local-state` แบบ writable และ output `/data/output` แบบ writable ฐานข้อมูลอยู่ในบริการ PostgreSQL เดิมและสำรองแยก ส่วน model weights อยู่กับ Model API owner แบบ read-only ไม่ mount เข้า Review image ต้องยืนยันก่อนใช้งานว่า approved image ใช้ `/app` และ workspace paths ตาม template จริง หากต่างออกไป ให้แก้ template ใน review แล้วตรวจใหม่ ห้ามเดา path บนเครื่องจริง

ตรวจโครงสร้างและข้อจำกัดแบบไม่อ่าน environment/secrets ได้ด้วย:

```powershell
python scripts/audit/validate_web_deployment_plan.py docs/audit/deployment-review-plan.json --compose-template docs/audit/review.compose.template.json
```

คำสั่งนี้ใช้ JSON parser และตรวจ Python syntax ของ healthcheck เท่านั้น ไม่เรียก Docker, ไม่ resolve .env และไม่เชื่อมต่อบริการ การ validate ด้วย Compose engine, image pull, boot, mount permission และ workload บน QA Cloud/โรงพยาบาลยังเป็น NOT_RUN อย่ารัน `docker compose config` พร้อม secret จริงแล้วแนบ output เพราะอาจเผย credential

Healthcheck ใน template อ่าน `/health` และรับเฉพาะ PASS/PASS_WITH_WARNINGS นี่เป็น semantic liveness เท่านั้น Readiness ก่อนให้แพทย์ใช้งานยังต้องมี receipt แยกครบสี่ส่วน: PostgreSQL SELECT 1 ผ่านช่องทางไม่แสดง credential, frontend source/output hashes ตรง release, workspace ที่ operator เลือกเปิดได้ และ model capability ที่พร้อมหรือข้อความ manual mode ที่ชัดเจน `/health` ไม่ได้รับรอง annotation quality, clinical ground truth หรือสิทธิ์ export

## Backup/restore procedure สำหรับ operator — ยังไม่ได้รัน

ฐานข้อมูลอย่างเดียวไม่ครอบคลุมภาพต้นฉบับ เพราะ source images อยู่ข้างนอก DB ให้แยก inventory อย่างน้อยหกชุด: PostgreSQL dump, workspace catalog/config ที่จำเป็น, original images พร้อม relative path/ขนาด/SHA256, snapshot outputs ที่อนุมัติ, app/frontend identity และ model asset hashes ของ owner เก็บ actual paths, permission records และ secrets เฉพาะที่จัดเก็บ private ของโรงพยาบาล ห้ามใส่ repo หรือ screenshot

1. เลือก release/ช่วงเวลาที่จะสำรองและบันทึกว่า writer ใดหยุดหรืออยู่ใน consistent snapshot ขณะ inventory ภาพและ workspace mapping ยืนยันปลายทางเข้ารหัส/สิทธิ์/พื้นที่ว่างกับ operator ก่อนดำเนินการ
2. สำรอง PostgreSQL แบบ consistent dump ด้วยเครื่องมือ major version ที่เข้ากับ server ใช้ service configuration และ password mechanism ของ operator โดยไม่ใส่ URL/password ใน command line ตัวอย่างต่อไปนี้เป็น placeholder เท่านั้น ชื่อ service และ path ต้องชี้ไปยัง scope ที่ได้รับอนุมัติไว้แล้ว

```text
pg_dump --dbname=service=APPROVED_BACKUP_SOURCE --format=custom --file=PRIVATE_BACKUP_PATH
pg_restore --list PRIVATE_BACKUP_PATH
```

3. สำรอง immutable originals และ workspace linkage inventory แยกจาก DB พร้อม hash ที่สัมพันธ์กับ snapshot source SHA256 ตรวจจำนวนไฟล์และ hash โดยไม่พิมพ์ patient filenames ออก log ส่วนที่ shared ให้ใช้ receipt ID และยอดรวม
4. เตรียม restore target ที่แยกจาก production/QA acceptance database และได้รับอนุมัติไว้ก่อน ห้ามใช้ฐานทดสอบของทีม Model API หรือชี้ restore กลับที่ต้นทาง ตัวอย่างนี้ไม่สร้าง DB และ audit ไม่ได้เรียกใช้

```text
pg_restore --dbname=service=APPROVED_ISOLATED_RESTORE_TARGET --no-owner --no-acl --exit-on-error PRIVATE_BACKUP_PATH
```

5. ตรวจ schema/migration version, workspace IDs, case count/revisions, grade/annotation confirmation hashes, snapshot row counts/file hashes และการเข้าถึง originals ที่ hash ตรง source records ความถูกต้องของ permission/role บนปลายทางต้องตรวจแยกจาก `--no-acl`; คำสั่งตัวอย่างไม่ได้ให้ clinician privileges
6. เปิดเฉพาะ release เดียวกันในสภาพแวดล้อม restore ที่อนุมัติและใช้ synthetic/manual smoke ตามแผน ห้ามชี้กลับไปส่งภาพโรงพยาบาลเข้า model service ระหว่าง rehearsal บันทึกเวลา restore, failures และผล reconciliation แล้วให้ operator/owner รับรองก่อนเรียกว่า restore ผ่าน

หาก app release ใหม่มีปัญหา ให้หยุดเฉพาะ process/service ที่ยืนยัน ownership ได้และคืน app/frontend artifact เดิมพร้อม config compatible ที่ตรวจแล้ว แพตช์นี้ไม่มี DB migration ถ้ามี clinical writes หลัง cutover ให้รักษา PostgreSQL ล่าสุดและประเมิน roll-forward ก่อน การ restore backup เก่าต้องมีการตัดสินใจเรื่อง writes ที่จะสูญเสียและสิทธิ์เฉพาะ ห้ามใช้การ rollback app เป็นเหตุล้าง source images, snapshots หรือ model weights

## Hospital annotation/training boundary

การเก็บ 100 ภาพสำหรับ train ต้องเก็บ clinical labels, completeness และ patient/eye/exam linkage ให้ครบแยกจาก operational screening completion ใช้ canonical snapshot exporter เดิม ไม่สร้าง CSV อีกระบบเพื่อข้าม permission เงื่อนไข hospital export ยังเป็น HTTP 409/no files ข้อมูลที่แพทย์ตรวจแล้วไม่ทำให้ export ถูกอนุมัติอัตโนมัติ reviewed-none เป็น completeness จน clinical owner อนุมัตินโยบาย negative ที่ระบุเวอร์ชัน ส่วน FOV/mask สำหรับเตรียม input ไม่ใช่ lesion segmentation label
