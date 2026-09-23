# บทพูดนำเสนอ Retinal Review Workbench

เอกสารนี้เป็นบทพูดสำหรับ HyperFrames deck ที่
[`hyperframes/index.html`](hyperframes/index.html) และไฟล์ offline ที่สร้างจาก
deck เดียวกันคือ [`RETINAL_REVIEW_DEMO.html`](RETINAL_REVIEW_DEMO.html)
มีฉากหลัก 19 ฉาก และ branch สำหรับคำถามด้าน clinical validation อีก 2 ฉาก
ใช้ `npx hyperframes present docs/presentation/hyperframes` เมื่อต้องการ
presenter mode แบบสด หรือเปิดไฟล์ offline เมื่อต้องการนำเสนอโดยไม่พึ่ง network

ใช้ `Space` หรือปุ่มลูกศรเพื่อไปฉากถัดไป และกลับจาก branch ด้วยคำสั่ง Back ของ
presenter ทุกฉากมีเวลาใน timeline ประมาณ 8 วินาที จึงสามารถพูดแบบเต็มหรือข้าม
ไปฉากถัดไปได้ตามเวลาที่มี

## Scene 01 — Retinal Review Workbench

เปิดด้วยภาพ retinal จริงที่ใช้เป็น upstream example และบอกกรอบให้ชัดว่า
Workbench นี้เป็นระบบช่วย review ที่ clinician ควบคุมเอง เป็น research POC
และไม่ได้อ้างว่าเป็นระบบวินิจฉัยอัตโนมัติ

**Truth label:** ภาพและ ROI เป็น upstream example ไม่ใช่ผล validation ของระบบนี้

## Scene 02 — ทำไม workflow นี้จึงสำคัญ

ภาพจำนวนมากมีคุณภาพ บริบท และความเร่งด่วนต่างกัน เป้าหมายของ Workbench คือ
ทำให้การ review เป็นขั้นตอนและตรวจสอบย้อนหลังได้ ลดงาน navigation ที่ไม่จำเป็น
และเก็บพื้นที่สำหรับ judgment ของจักษุแพทย์ไว้เสมอ

**Truth label:** เป็น conceptual framing ไม่มีตัวเลขผลลัพธ์ของโครงการ

## Scene 03 — ระบบเป็นอะไรและไม่เป็นอะไร

ระบบเป็น assistive review layer ที่แสดง evidence พร้อม provenance ช่วยบันทึก
การตัดสินใจและ dataset workflow แต่ไม่ใช่ autonomous diagnosis, treatment
decision, patient notification หรือสิ่งทดแทน judgment ของจักษุแพทย์

## Scene 04 — ขอบเขตของรุ่นแรก

ขอบเขตปัจจุบันเริ่มจาก color fundus photography และ supported single-frame
ophthalmic DICOM ผ่าน model evidence แบบเลือกใช้ได้ ไปสู่ human review และ
export ที่เก็บ provenance ส่วน integration อื่นที่ยังไม่ได้ทำไม่ควรถูกพูดว่า
มีแล้ว

## Scene 05 — ทีมที่อยู่เบื้องหลัง workflow

ผังนี้ถอดจากไฟล์ organization chart ที่เจ้าของงานให้มา แสดง Watcharin Buason
เป็น Managing Director และแสดงอีกหก role ตามแหล่งต้นฉบับโดยไม่เพิ่มความสัมพันธ์
หรือประวัติที่ไม่ได้อยู่ในเอกสารอ้างอิง

## Scene 06 — สมาชิกและบทบาท

แสดงสมาชิกทั้งเจ็ดคน: Watcharin Buason, Benjamaporn Jeankor, Dependa,
Thiphornphan Uthaithat, Siripon Srihangpiboon, Patthadon Changate และ
Sansern Makcharoen ภาพ portrait มีเฉพาะห้าคนตามไฟล์ต้นทาง ดังนั้นอีกสองคนใช้
initials เพื่อไม่สร้างภาพหรือ biography ขึ้นเอง

**Truth label:** Portraits เป็น owner-provided source; ไม่มีการอนุมาน biography

## Scene 07 — AI architecture

งาน global DR grading และ lesion ROI เป็น evidence คนละแบบ ทั้งสองอย่างอยู่
ใต้ human review decision ผลของ AI ช่วยให้ตรวจและถามคำถามได้ แต่ไม่สามารถยืนยัน
case แทน clinician

## Scene 08 — RETFound

RETFound เป็นบริบทของ retinal foundation-model research ส่วน identity ของ
product path ปัจจุบันคือ `retfound-aptos5` ซึ่งให้ข้อเสนอ DR ห้าระดับ คะแนนเป็น
model evidence ไม่ใช่ calibrated clinical probability และผล upstream ไม่ใช่
local validation

## Scene 09 — PRISM-DR

PRISM-DR ช่วยเสนอบริเวณที่อาจเป็น Microaneurysm, Hemorrhage, Hard exudate
หรือ Soft exudate แพทย์สามารถใช้ แก้ หรือลบ suggestion ได้ ผลลัพธ์ว่างหมายถึง
ไม่มี suggestion ในครั้งนั้น ไม่ใช่หลักฐานว่าไม่มี lesion

## Scene 10 — ความไม่แน่นอนต้องมองเห็นได้

ภาพที่อ่านไม่ได้ไม่เท่ากับภาพปกติ และไม่มี detection ไม่เท่ากับไม่มี lesion
ระบบควรทำให้ limitation และ uncertainty ชัดเจน เพื่อให้ clinician ทำตาม
local clinical pathway ได้ ไม่เปลี่ยนความไม่แน่นอนให้เป็น normal โดยอัตโนมัติ

## Scene 11 — ขอบเขตการเลือกภาพ

Workbench รับภาพที่ถูกเลือกและอนุมัติแล้วจาก approved staging ไม่ได้ browse
เข้าไปเลือกภาพจาก hospital storage เอง การควบคุม storage อยู่ที่โรงพยาบาล
และทีมโครงการติดตาม coverage ภายนอก workflow ปกติของ clinician

## Scene 12 — เส้นทางของหนึ่ง case

เริ่มที่ Confirm Image เพื่อตรวจ pseudonymous context และ eye จากนั้น Review
ภาพและ optional AI evidence แล้วเลือกและยืนยัน Confirm final DR grade จากนั้น
จึงเข้า annotation loop เมื่อจำเป็นและไปต่อที่ next case

**Truth label:** เป็น current Phase-1 clinician workflow

## Scene 13 — Worklist และ Confirm Image

เลือก case ที่ถูก stage ใน Worklist แล้วตรวจ patient key และ laterality ใน
Confirm Image filename เป็นเพียง evidence ประกอบ ไม่ใช่ตัวตัดสินแทน context
ที่ผู้ใช้ยืนยัน

**Truth label:** เป็น current UI screenshot จาก public/synthetic fixture

## Scene 14 — Review พร้อม AI evidence แบบเลือกใช้

ภาพ retinal ได้พื้นที่หลักของหน้าจอ RETFound แสดงข้อเสนอ DR และ PRISM-DR
แสดงข้อเสนอ ROI การเปิด evidence เป็นตัวเลือก และ human decision ยังแยกจาก
model output เสมอ

**Truth label:** ภาพ retinal และ ROI เป็น upstream example ที่ติดป้ายไว้ชัดเจน

## Scene 15 — การตัดสินใจหลักหนึ่งครั้ง

จุดตัดสินใจคือการเลือกและยืนยัน final DR grade อย่างชัดเจน ระบบไม่ยืนยัน
grade จนกว่าจะมีการเลือกเกรดของ clinician

## Scene 16 — Annotation เมื่อจำเป็น

เปิด annotation editor เฉพาะเมื่อจำเป็นต่อ human evidence กด ROI เพื่อเลือก
confirm, correct หรือ remove แล้วจึง confirm annotation ชุดปัจจุบัน ผล AI เดิม
อย่าง class, score, geometry และ provenance ยังต้องตรวจสอบย้อนหลังได้

## Scene 17 — DICOM และ grouped export

ต้นฉบับยัง immutable ระบบใช้ decoded/rendered derivative สำหรับการแสดงผล
coordinate และ annotation จากนั้น export เป็นกลุ่มตาม readiness พร้อม manifest,
hash และ provenance ของ DICOM การอ่าน modality ที่ไม่รองรับหรือ decode ล้มเหลว
ต้องคง status เฉพาะของมันไว้

## Scene 18 — Deployment boundary

Windows review workstation ใช้ `APP_PROFILE=review` และ `MODEL_RUNTIME=remote`
โดยไม่เก็บ model weights ส่วน Linux GPU Model API ใช้ `APP_PROFILE=model_api`
ตรวจ asset และ CUDA ภายใน protected hospital boundary ทั้งสอง role แยกกัน
และ review workflow ยังทำงานใน local state ได้เมื่อ model assistance ใช้ไม่ได้

## Scene 19 — สิ่งที่ต้องการจากจักษุแพทย์

ปิดด้วยคำถามเรื่อง workflow fit, evidence ที่ช่วยตัดสินใจจริง, การจัดการ
ungradable image, trigger ของ uncertainty handling และวิธี validation ที่เหมาะกับ
human-AI team เป้าหมายคือทำให้ระบบช่วยการ review ได้จริงโดยไม่ลดอำนาจการตัดสินใจ
ของ clinician

## Branch — Clinical validation questions 1

ใช้ branch นี้ถามว่า global DR evidence หรือ lesion evidence แบบใดเปลี่ยน
next clinical action ได้จริง และ visual cue แบบใดช่วย inspection, correction
หรือ escalation branch นี้เป็น discussion prompt ไม่ใช่ product claim

## Branch — Clinical validation questions 2

ถามต่อเรื่อง wording และ local pathway สำหรับ ungradable image รวมถึง study
design ที่ประเมิน human-AI team ร่วมกัน ไม่ใช่ดู model score แยกเดี่ยว จากนั้น
กด Back เพื่อกลับสู่ main line

## ข้อควรระวังในการพูด

- อย่าเรียก model score ว่า clinical probability ที่ calibrate แล้ว
- อย่าพูดว่าไม่มี lesion เพียงเพราะ PRISM-DR ไม่มี detection
- อย่าพูดว่า UI เป็นระบบ login หรือ electronic signature หากไม่ได้ทำไว้
- ใช้เฉพาะ workspace ที่เป็น synthetic หรือ public ในการสาธิต
- อ้างอิง [`PRESENTATION_SOURCE_MAP.md`](PRESENTATION_SOURCE_MAP.md) เมื่อมีคำถามเรื่องภาพ, model provenance หรือ source path
