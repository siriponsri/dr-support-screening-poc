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

- ที่หน้า Sign in มีปุ่ม EN และ TH ให้เลือกภาษาที่สะดวกค่ะ ไม่เลือกก็ใช้งานได้
- จากนั้นใส่ username และ password ที่ผู้ดูแลระบบให้ไว้ค่ะ
- หากต้องการดูวิดีโอนี้อีกครั้ง กดปุ่ม ดูวิธีใช้งาน ได้ค่ะ
- หน้า Today จะสรุปงานของวันนี้ให้ค่ะ
- ว่ามีภาพรอตรวจกี่ภาพ และภาพใดที่ต้องยืนยันก่อน

## worklist: Worklist, Scan input folder

- ภาพใหม่จะมาจากโฟลเดอร์นำเข้าของ Workspace ค่ะ
- ที่หน้า Worklist กดปุ่ม สแกนโฟลเดอร์นำเข้า
- ภาพจะขึ้นในรายการ โดยระบบไม่แตะไฟล์ต้นฉบับค่ะ

## confirm: Confirm Image

- ก่อนเริ่มตรวจ กดปุ่ม Confirm Image ค่ะ
- เลือกชนิดภาพให้ตรงกับภาพที่ถ่ายมา
- ภาพจอตาวงกลมบนพื้นดำแบบนี้ คือ CFP
- ส่วนภาพมุมกว้างที่เห็นขนตาหรือขอบสีเหลือง คือ UWF ค่ะ
- หากไม่แน่ใจ เลือก ยังไม่แน่ใจ ไว้ก่อน แล้วสอบถามผู้ถ่ายภาพได้ค่ะ
- ภาพตัวอย่างนี้เป็น CFP จากนั้นเลือกตาข้างที่ถ่าย แล้วกดยืนยันภาพค่ะ

(ระหว่างประโยคที่ 3 ถึง 5 มีการ์ดเทียบภาพ CFP กับ UWF ขึ้นบนจอ)

## ai: Review: AI grade suggestion (demo)

- ถ้าเชื่อมต่อ AI ไว้ ระบบจะเสนอ DR grade ให้ดูประกอบ
- แต่เป็นแค่คำแนะนำนะคะ คนตัดสินคือแพทย์เสมอ
- ผล AI ในวิดีโอนี้เป็นข้อมูลจำลอง

## grade: Clinician Review: confirm or correct the DR grade

- ที่หน้า Clinician Review แพทย์พิจารณาภาพ แล้วเลือกเกรดสุดท้ายค่ะ
- จะยืนยันตามคำแนะนำของ AI หรือแก้เกรดก็ได้
- ในตัวอย่างนี้ แพทย์แก้เป็นเกรด 3 แล้วกด Confirm DR grade ค่ะ

## annotate: Annotation Editor, Finish image

- ใน Annotation Editor วาดกรอบรอบรอยโรคที่ต้องการบันทึกได้ค่ะ
- เลือกชนิดรอยโรค ระบบจะบันทึกให้อัตโนมัติ
- เมื่อเสร็จแล้ว กด Finish image เพื่อไปยังภาพถัดไปค่ะ

## report: Screening report, Referrals

- ใน Screening report พยาบาลสามารถเตรียมข้อมูลไว้ล่วงหน้าได้ค่ะ
- ผู้ให้เกรดเป็นผู้เลือกเองว่า Refer หรือ Not refer
- จากนั้นแพทย์ลงนาม ระบบจะไม่ตัดสินการส่งต่อแทนแพทย์ค่ะ
- เคสที่เลือก Refer จะไปอยู่ในหน้า Referrals
- ติดตามได้สะดวกจากที่เดียวค่ะ

## datasets: Datasets

- หน้า Datasets ใช้สำหรับส่งออกชุดข้อมูลวิจัยค่ะ
- ภาพที่ยืนยันเกรดแล้วจะอยู่ในกลุ่ม DR-ready
- การส่งออกเป็นการคัดลอก ไม่แก้ไขภาพต้นฉบับค่ะ

## outro: End card

- โปรแกรมนี้ไม่ใช่เครื่องมือวินิจฉัยโรค
- เกรดที่แพทย์ยืนยันคือผลที่ใช้จริง
- ภาพที่ส่งไป server ของทีม ต้องเป็นภาพสาธารณะ
- หรือภาพที่ได้รับความยินยอมเท่านั้น ขอบคุณค่ะ
