# แผน MS-03: Model API แบบ session มีขอบเขต และทดสอบ watchdog/OOM (dr-train GPU0)

สถานะ: **เสนอให้ owner อนุมัติ** / 25 ตุลาคม 2569 / จัดทำโดย Claude Code / ต่อจาก HANDOFF §28 และ §31

owner อนุมัติแนวทางแล้ว (25 ต.ค.): ทำเป็น session ที่มีขอบเขต ไม่ใช่บริการเปิดตลอด และเตรียมแผนกับ proposal hash ให้ยืนยันก่อนใช้ GPU

## 1. เป้าหมาย

1. พิสูจน์ว่าเมื่อหน่วยความจำหรือเวลาเกินกำหนด ระบบหยุดงานเองอย่างปลอดภัย ไม่ทำให้ GPU ทั้งเครื่องเต็ม และไม่กระทบ Ollama หรืองานทีม
2. เปิด Model API เป็น session ที่มีขอบเขตให้หน้าแอปเรียกใช้จริง: เริ่ม, ดูสถานะ, รับงานตามรายการที่อนุมัติ, หยุด และเก็บกวาดครบ

## 2. ขอบเขตที่ขออนุมัติ

| รายการ | ค่า |
| --- | --- |
| เครื่อง / GPU | dr-train เฉพาะ **GPU0** / ไม่แตะ GPU1 และ Ollama / ตรวจก่อนเริ่มว่า GPU0 ว่าง ถ้าไม่ว่างจะไม่เริ่ม |
| เฟส A: watchdog/OOM | process ทดสอบแยก **ไม่มีน้ำหนักโมเดล ไม่มีภาพ** / จำกัด GPU memory fraction 1.5 GiB และเพดานของ supervisor ที่ต่ำ (VRAM 2 GiB, RAM 4 GiB, เวลาต่อ request 10 วินาที) / ทดสอบ: OOM ภายในเพดาน, VRAM เกิน, RAM เกิน, request ช้าเกิน และ hard alarm / **inference requests = 0** / GPU lease **≤ 900 วินาที** / ทำตอนที่ service หยุดอยู่ |
| เฟส B: service session | โหลด USPEC, RETFound และ PRISM ครั้งเดียว / GPU lease **≤ 3,600 วินาที** / requests สูงสุด **6** จากโควตา post-fix ที่จองไว้: USPEC 2 (UWF), RETFound 2 (CFP), PRISM 2 / ใช้ภาพ post-fix ที่คัดลอกเข้า private roots แล้ว (รายการภาพที่แน่นอนอยู่ใน proposal) / ทุก request ผ่านหน้าแอป มี readback อิสระ / ไม่มี retry / ถ้ามีครั้งใดล้มเหลวหรือไม่แน่ชัด หยุดทันทีและปิด session |
| Workspace / ผู้ตรวจ | TEST_ONLY workspace `ws_m1_63ed86c7…` / `TEST_ONLY_ENGINEERING` (ไม่ใช่ผลแพทย์) |
| การเชื่อมต่อ | SSH tunnel แบบ loopback เท่านั้น / ไม่เปิด listener สาธารณะ (0.0.0.0) / ไม่ใช้ `start.sh` หรือ systemd unit เดิม |

## 3. ลำดับการทำงาน

**เฟส A (watchdog/OOM)**
1. บันทึกหน่วยความจำ GPU1 และ PID ของ Ollama ก่อนเริ่ม
2. รัน process ทดสอบแยกตามกรณีในข้อ 2 ทีละกรณี ตรวจว่า supervisor หยุดงานและเก็บกวาดเอง
3. บันทึก GPU1 และ Ollama หลังจบ ต้องไม่เปลี่ยน / GPU0 กลับมาว่าง
4. ถ้าข้อใดไม่ผ่าน: หยุด ไม่ไปเฟส B และรายงาน

**เฟส B (service session, เฉพาะเมื่อเฟส A ผ่าน)**
5. เริ่ม session / ตรวจ status (app reachable, DB ready, models loaded, protocol bound) แยกเป็นระดับ
6. ส่งงานจากหน้าแอปตามรายการ 6 งาน ทีละงาน / readback แต่ละงานก่อนงานถัดไป
7. หยุด session / ยืนยัน `COMPLETE.json` (cleanup, window stop, ledger close = CONFIRMED) / GPU0 คืนว่าง

## 4. โควตาคงเหลือ

| รายการ | ตอนนี้ | หลังแผนนี้ (กรณีใช้ครบ) |
| --- | --- | --- |
| Requests (cap 549) | ใช้ 534 / เหลือ **15** (Local 6, post-fix 9) | ใช้ ≤ 540 / เหลือ **≥ 9** (Local 6, post-fix 3) |
| GPU-seconds ใหม่ (งบรวม 21,600) | ใช้ 14,400 / เหลือ **7,200** | ใช้ ≤ 18,900 / เหลือ **≥ 2,700** |

lease คิดเต็มจำนวนแบบ conservative แม้ใช้จริงน้อยกว่า / ไม่มี refund / ไม่ต่ออายุ

## 5. สิ่งที่ต้องทำก่อนใช้ GPU (ไม่ใช้ GPU, ไม่คิด request)

1. **การตัดสินใจทางบัญชีใหม่ + โค้ด** (branch แยก): decision `HOSPITAL_M1_ACCOUNTING_SERVICE_20261025` ต่อจาก decision PRISM ที่ปิดแล้ว (ผ่าน fence handover) / window A ≤ 900 วินาที และ window B ≤ 3,600 วินาที / operation list 6 งานผูก source_sha256 / cap ยัง 549 / ไม่แตะ Local 6 / มี tests และ review อิสระก่อน merge
2. **process ทดสอบ watchdog/OOM** แบบไม่มีน้ำหนักโมเดล และ config supervisor สำหรับทดสอบ / จำกัดทรัพยากรด้วย prlimit และ nice (ตรวจแบบอ่านอย่างเดียวว่ามี cgroup ให้ใช้หรือไม่)
3. **Proposal v1** สร้างจากโค้ดที่ merge แล้ว และตรวจ dry run บน dr-train แบบ CPU
4. Deploy โค้ดโฮสต์ชุดใหม่และตรวจ identity แบบ CPU (pins ต้องตรง)

**การยืนยันอีกครั้งเดียว:** ผมจะส่ง SHA-256 ของ proposal ให้ยืนยันด้วยปุ่มเดียว หลังยืนยันจึงเริ่ม GPU ตามแผนนี้

## 6. ไม่อยู่ในแผนนี้

- บริการเปิดตลอด, autostart หรือ systemd / ไม่ขยายเพดานเวลาของ child ที่ freeze ไว้
- QA_LOCAL และโควตา Local 6
- ไม่เปลี่ยน pins, preprocessing หรือความหมายทางคลินิก
- ผลเป็นหลักฐานทางวิศวกรรมบนข้อมูล TEST_ONLY ไม่ใช่การรับรองทางคลินิก
