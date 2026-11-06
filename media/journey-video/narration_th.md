# Journey video narration (Thai)

Voice: Google `gemini-3.8-flash-tts`, prebuilt voice **Achernar** (female), soft and slow.
The owner's style line goes with every request:

> อ่านด้วยเสียงผู้หญิงที่นุ่มนวล อบอุ่น ใจเย็น พูดช้า ๆ ไม่รีบร้อน เว้นจังหวะหายใจระหว่างประโยค:

Sent as a bare prefix the model also read that line aloud, so `tts.py` sends it as director's notes
above the transcript (the same words, not spoken). Only this narration text goes to Google.

`scenes.json` is the source the scripts read; keep this file in step with it.
Each row below is one caption line; the lines of a scene are one request and one WAV.

## intro: Title card

- วิดีโอนี้จะพาดูการใช้งาน Retinal Review Workbench
- ตั้งแต่เข้าสู่ระบบ จนถึงส่งออกชุดข้อมูล
- ภาพทั้งหมดในวิดีโอเป็นข้อมูลตัวอย่างค่ะ

## signin: Sign in, Today

- เริ่มจากหน้า Sign in กดปุ่ม TH เพื่อใช้ภาษาไทย
- แล้วใส่ username กับ password ที่ผู้ดูแลระบบให้ไว้
- กดปุ่ม ดูวิธีใช้งาน เพื่อเปิดวิดีโอนี้อีกครั้ง
- หน้า Today สรุปงานของวันนี้
- ว่ามีภาพรอตรวจกี่ภาพ และภาพไหนต้องยืนยันก่อน

## worklist: Worklist, Scan input folder

- ภาพใหม่มาจากโฟลเดอร์นำเข้าของ Workspace
- ที่หน้า Worklist กด สแกนโฟลเดอร์นำเข้า
- แล้วภาพจะขึ้นในรายการ โดยไม่แตะไฟล์ต้นฉบับ

## confirm: Confirm Image

- ก่อนเริ่มตรวจ กด Confirm Image
- เลือกชนิดภาพเป็น CFP ใส่รหัสผู้ป่วยแบบไม่ระบุตัวตน
- เลือกตาข้างที่ถ่าย แล้วกดยืนยันภาพ

## ai: Review: AI grade suggestion (demo)

- ถ้าเชื่อมต่อ AI ไว้ ระบบจะเสนอ DR grade ให้ดูประกอบ
- แต่เป็นแค่คำแนะนำนะคะ คนตัดสินคือแพทย์เสมอ
- ผล AI ในวิดีโอนี้เป็นข้อมูลจำลอง

## grade: Clinician Review: confirm or correct the DR grade

- ที่หน้า Clinician Review แพทย์ดูภาพแล้วเลือกเกรดสุดท้าย
- จะยืนยันตาม AI หรือแก้เกรดก็ได้
- ตัวอย่างนี้แพทย์แก้เป็นเกรด 3 แล้วกด Confirm DR grade

## annotate: Annotation Editor, Finish image

- ใน Annotation Editor วาดกรอบรอบรอยโรคที่ต้องการบันทึก
- เลือกชนิดรอยโรค ระบบบันทึกให้อัตโนมัติ
- เสร็จแล้วกด Finish image เพื่อไปภาพถัดไป

## report: Screening report, Referrals

- ใน Screening report พยาบาลเตรียมข้อมูลไว้ได้
- ผู้ให้เกรดเลือกเองว่า Refer หรือ Not refer
- แล้วแพทย์ลงนาม ระบบไม่ตัดสินการส่งต่อแทน
- เคสที่เลือก Refer จะไปอยู่ในหน้า Referrals
- ติดตามได้จากที่เดียว

## datasets: Datasets

- หน้า Datasets ใช้ส่งออกชุดข้อมูลวิจัย
- ภาพที่ยืนยันเกรดแล้วอยู่ในกลุ่ม DR-ready
- การส่งออกเป็นการคัดลอก ไม่แก้ภาพต้นฉบับ

## outro: End card

- โปรแกรมนี้ไม่ใช่เครื่องมือวินิจฉัยโรค
- เกรดที่แพทย์ยืนยันคือผลที่ใช้จริง
- ภาพที่ส่งไป server ของทีม ต้องเป็นภาพสาธารณะ
- หรือภาพที่ได้รับความยินยอมเท่านั้น ขอบคุณค่ะ
