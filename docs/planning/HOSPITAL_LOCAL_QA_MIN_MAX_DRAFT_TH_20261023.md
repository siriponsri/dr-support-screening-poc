# DR Screening: ผลทดสอบ ปัญหา และร่าง minimum / maximum spec สำหรับ hospital local QA

วันที่ 23 ตุลาคม 2569 · สถานะ **DRAFT — READY_FOR_REVIEW**

ฐานโค้ดที่ตรวจ: `db3f945c1c8c5fd89bb23ae3e854e2f035fa61af` เอกสารนี้เสนอทรัพยากรและเกณฑ์รับระบบสำหรับ QA ภายในโรงพยาบาล ยังไม่ใช่สเปกขั้นต่ำที่พิสูจน์ด้วยการลดทรัพยากร ไม่ใช่ผล load test ของเครื่องโรงพยาบาล และไม่ใช่ clinical acceptance

คำว่า **minimum** หมายถึงชุดตั้งต้นที่เสนอให้ทดสอบแบบผู้ใช้หลักหนึ่งคนและ inference ทีละงาน ส่วน **maximum** หมายถึงกรอบบนที่เสนอสำหรับ QA ชุดนี้เพื่อเผื่อทรัพยากรและการดูแลระบบ ไม่ใช่ขีดความสามารถสูงสุดหรือจำนวนผู้ใช้ที่รับรองแล้ว

ตัวเลขในหัวข้อ 1–3 เป็นข้อสังเกตจากหลักฐานที่เก็บไว้ ตัวเลข hardware, network, retention และ recovery targets ในหัวข้อ 4–6 เป็นข้อเสนอที่อนุมาน ต้องยืนยันกับ IT และทดสอบบนเครื่องเป้าหมาย การรับร่างนี้ไม่อนุมัติ GPU requests เพิ่ม การเปลี่ยนสิทธิ์ เครือข่าย credentials หรือ deployment โดยอัตโนมัติ

## 1. ผลที่ตรวจได้

| รายการ | ผลจริงและขอบเขต |
| --- | --- |
| ภาพไม่ซ้ำ | 240 ภาพ: UWF 186 และ CFP 54 ไม่ใช่จำนวนผู้ป่วย |
| งานที่วางแผน | 480 งาน: PRISM 240, USPEC 186, RETFound 54 รวม representative เดิมแล้ว |
| ผลตรงกับ PostgreSQL | 467 งาน: USPEC 184, RETFound 53, PRISM 230 ผ่าน response/saved-entry hash และ fresh SQL readback |
| งานที่ไม่ผ่าน | FAILED_NO_RETRY 9: USPEC 2, RETFound 1, PRISM 6; BLOCKED_PREMODEL 4 เป็น PRISM ไม่มีงานค้างหรือ uncertain ใน ledger ของ batch นี้ |
| การนับ requests | 476 attempt intents ของ batch + ประวัติเดิม 49 = 525/529 ไม่มี automatic inference retry ไม่ reset ledger ไม่ส่ง terminal jobs ซ้ำ ยอดเก่า 49 ยังคงเดิม รวมสถานะเก่าที่เคยส่งไม่ชัดเจนโดยไม่ replay |
| GPU | GPU0 RTX 2080 Ti 11 GB เท่านั้น [1] ไม่ใช่ผล multi-GPU หรือ T4 comparison |
| เวลาและงบ | รอบที่อนุมัติเพิ่มคิดงบ GPU แบบ conservative 9,800.644/10,800 วินาที; รอบเดิมคง 4,772.230 วินาที รวม 14,572.874 วินาที **ข้ามสอง session** ไม่ใช่การใช้เกินเพดานใน session เดียว |
| Wall time รอบใหม่ | ขอบบนถึงเวลาที่สังเกต process จบ 10,616.657/14,400 วินาที รวมช่องว่างรอ polling ไม่ใช่ GPU compute occupancy หรือ benchmark throughput |
| Cleanup | รอบสุดท้ายยืนยันครบ ไม่มี active lease/quarantine; ประวัติ cleanup failure และ owner recovery เก็บไว้ ไม่ถูกเขียนทับ |
| Export ใหม่ | records 240 แถว, สำเนาภาพแบบ byte-preserving 160 ภาพใน UNREVIEWED, ข้าม 80 ภาพตาม admission เดิม; DR labels 0, lesion labels 0 ไม่สร้าง gold อัตโนมัติ |
| Local workflow | main app + ภาพจริง UWF/CFP สองภาพ + AI จำลอง → PostgreSQL → export → Chrome ผ่าน แยกจาก inference จริงข้างต้น |
| Source validation | backend ของ branch control-source 1,094 ผ่าน / 40 skipped; targeted main regression 13 ผ่าน; app core เดิมผ่าน backend 1,081 / 40 skipped และ frontend 284, typecheck/build โดย tree ของ app/frontend ตรงกับรุ่นที่ qualified |
| หน้าจอใช้งานจริง | เปิด main ได้และ CUA เห็น Worklist 21 ภาพใน workspace เดิม แต่ main ยัง SERVER_RUNNING / MANUAL_MODE ไม่ใช่ workspace ของ batch ใหม่ |
| Browser evidence | 9 screenshots จาก representative เดิม 4 งาน มี USPEC จริงที่ผ่านถึง PostgreSQL; RETFound เดิมล้มเหลว และ PRISM representative สองงานหยุดก่อน inference ไม่อ้าง browser E2E ผ่านครบสามโมเดล |
| HTML | gallery 240 ภาพ, สถานะ 480 งาน, provenance/timings/errors และ scientific ROI overlays; local links/hash และ inline JavaScript syntax ผ่าน ส่วน browser visual smoke ยัง BLOCKED |

ผลทางเทคนิคข้างต้นไม่ให้ค่า sensitivity, specificity, grading agreement, calibration, false-positive reduction หรือเวลาที่ประหยัดให้แพทย์ และไม่ทำให้ PRISM UWF ที่ยัง experimental กลายเป็นโมเดลที่ผ่าน clinical validation

## 2. ตัวเลขที่ใช้ประกอบการ sizing

สรุปใหม่จาก retained receipts โดยไม่เรียกโมเดล/QA/DB เพิ่ม มี resource receipts 117 leases ค่า VRAM เป็น sampled maximum ของ GPU0 ส่วน RAM เป็น `VmRSS` ของ owned worker PID เพียงตัวเดียว ไม่ใช่ RAM รวมของ host/process tree และอาจไม่เห็น spike ระหว่างจุด sampling

| โมเดล | Sampled VRAM สูงสุด | Worker RSS สูงสุด | Median execute ใน worker | Median app request รวม save | Median whole job รวม prepare/readback |
| --- | ---: | ---: | ---: | ---: | ---: |
| RETFound | 1,380 MiB | 3.04 GiB | 0.294 s | 0.891 s | 1.031 s |
| USPEC | 1,444 MiB | 3.04 GiB | 1.402 s | 4.062 s | 4.211 s |
| PRISM | 5,442 MiB ≈ 5.31 GiB | 2.43 GiB | 11.765 s | 26.062 s | 36.008 s |

เวลาในตารางใช้เฉพาะงาน PASS_READBACK ขนาดภาพ/โมเดล/เส้นทางต่างกัน จึงไม่ใช้จัดอันดับความเร็วโมเดล PRISM whole-job p95 ประมาณ 81.422 s และสูงสุด 109.375 s; worker execute สูงสุดประมาณ 20.679 s การโหลดและตรวจ identity ต่อ lease อยู่ระดับประมาณ 8–25 s ตามโมเดล ไม่รวมไว้เป็น cold-start SLA ของผู้ใช้

ยังไม่ได้วัด host CPU utilization, core requirement, host RAM peak, disk IOPS, LAN RTT/throughput, concurrent users หรือการ resident ทุกโมเดลพร้อมกัน จึงไม่อนุมานว่ารวม VRAM ของสามโมเดลแล้วเปิดพร้อมกันได้ และไม่ใช้ sampled 5.31 GiB ไปสรุปว่า GPU 6–8 GB เพียงพอ

ข้อมูล storage ที่เห็นจริงแยกตามตำแหน่ง:

| ข้อมูล | ขนาด |
| --- | ---: |
| ภาพต้นฉบับไม่ซ้ำ 240 ภาพฝั่ง workstation | 1,036,118,254 bytes ≈ 1.04 GB |
| ภาพต้นฉบับเฉลี่ย / p95 / ใหญ่สุด | 4.32 / 7.22 / 9.32 MB |
| ความละเอียดสูงสุดตามจำนวน pixels | 15,944,033 pixels; ตัวอย่าง UWF 3997 × 3989 |
| Project directory ที่ monitor ฝั่ง GPU สูงสุด | 19,537,040,430 bytes ≈ 19.54 GB รวม assets/stages ใน directory นั้น ไม่ใช่ disk รวมทั้งเครื่อง |
| Snapshot ล่าสุดฝั่ง workstation | ประมาณ 645.85 MB รวมสำเนาภาพ 160 ภาพ |
| HTML/JSON/CSV/derived gallery ชุดล่าสุด | ประมาณ 240.63 MB |

นี่เป็น retained footprint ของชุดนี้ ไม่ใช่ขนาดติดตั้งทั้งหมดหรือ storage ต่อปี ภาพถูก encode เป็น JSON/base64 ระหว่างบาง transport จึงต้องเผื่อ payload ใหญ่กว่าไฟล์ต้นฉบับ

## 3. ปัญหาที่พบและสถานะ

แยก defect ที่พิสูจน์/แก้แล้วออกจากเหตุการณ์เก่าที่ไม่มีรายละเอียดพอ การผ่าน regression ไม่เปลี่ยน failed job เดิมให้เป็น PASS

| ID | ปัญหา / หลักฐาน | การจัดการและข้อค้าง |
| --- | --- | --- |
| Q01 | C02 ยัง isolated; B03 เปลี่ยน path/ชื่อและยังไม่ freeze/test | รวม source ที่ตรวจได้ตาม branch/worktree, ตรวจ package/build identities และ freeze ตาม revision เก็บ candidate เดิมไว้ ไม่ใช้คำสั่งเก่าแทนรุ่นใหม่ |
| Q02 | C02 postimage ทำ baseline `read_original_case` หาย; 17 regression failures | คืน read-only method เดิมพร้อม revision/identity checks โดยไม่เปลี่ยน schema หรือ clinician semantics |
| Q03 | Assertions/fixtures บางส่วนตาม contract เก่า และ fixture imports ทำ lint ไม่ผ่าน | แก้เฉพาะ synthetic fixtures/expectations ให้ตรง approved policy ไม่ลด admission/clinical checks ผล suite สุดท้ายตามหัวข้อ 1; 40 skipped ไม่ถูกนับเป็นผ่าน |
| Q04 | Git บน Windows แปลง LF เป็น CRLF ทำ byte-pinned algorithm hash ไม่ตรง | ใช้ scoped LF attributes และ materialize เฉพาะ blobs ที่ตรวจ preimage แล้ว ไม่เปลี่ยน expected hash หรือ algorithm |
| Q05 | เขียน evidence ก่อน/หลังทำงานล้มเหลวแล้วอาจข้าม cleanup | แยก evidence-write failure, ให้ cleanup ยังถูกเรียก และรายงาน blocked/fail-closed เมื่อ receipt ไม่ครบ มี negative regressions ก่อนแก้ |
| Q06 | Batch inherit source scan roots และ environment ไม่ตรง deployment | จำกัด input ตาม manifest, scope/restore environment เดิม ไม่สแกน root อื่น ไม่เพิ่มสิทธิ์ภาพ |
| Q07 | Hospital app opt-in ไม่ครบ; worker environment ไม่เห็น token เดิมที่จำเป็น | ซ่อม scoped opt-in/token ของ runtime เดิมและคืนค่าเมื่อจบ ไม่ใส่ secret ใน argv/UI/Git; first RETFound failure เก่าไม่มี response status เก็บไว้ จึงไม่ระบุย้อนหลังว่าเกิดจาก flag อย่างแน่นอน |
| Q08 | Resume ชน exclusive-create staging receipt ที่เหมือนเดิม | Read back เมื่อ bytes/identity ตรงกัน; ถ้าต่างยัง block เก็บ remote stages แบบ immutable ไม่ทับของเดิม |
| Q09 | PRISM transport ขาด model metadata ทำ panel ไม่แสดง | Batch-only metadata wrapper ตรวจ pins และ modalities ที่ได้รับอนุมัติ โดยคง ready=false/research warnings ไม่ promote clinical eligibility |
| Q10 | Automation คลิก hidden Chakra input แล้วไม่เกิด checked state | เปลี่ยนเป็น visible label click และ assert checked state; fixture Chrome regression ผ่าน แต่ representative เดิมยัง BLOCKED_PREMODEL และไม่ replay |
| Q11 | Lease เก่ารายงาน aggregate cleanup=false แม้ worker/ports บางส่วนปิดแล้ว | Quarantine/lock และคิด reservation เต็ม 600 s; owner อนุมัติ recovery เฉพาะ lease โดยเก็บ ledger/เวลา/receipt เดิม ไม่มี refund หรือ generic auto-clear |
| Q12 | Uvicorn graceful shutdown 5 s แข่งกับ join 5 s | Reproduce race แล้วเพิ่ม join margin เป็น 6.5 s พร้อม named cleanup components; ไม่อ้างว่านี่พิสูจน์ missing component ของเหตุการณ์ Q11 ย้อนหลัง |
| Q13 | USPEC HTTP503: เหตุการณ์แรกไม่มี RPC detail; เหตุการณ์ถัดไป payload 8.36 MB ถูก reject หลังประมาณ 5.17 s ก่อน dispatch | Reproduce slow ingress 5 s แล้วใช้ finite-batch ingress 15 s; แยกจาก normal defaults ไม่ย่อ/recompress ภาพ และไม่อ้าง historical503 ทุกงานเป็นสาเหตุเดียวกัน |
| Q14 | PRISM preparation มี body+CPU span เดิม 5 s แม้ channel/gateway อื่นยาวกว่า | Regression ยืนยัน bottleneck แล้วกำหนด batch-only child preparation 15 s / channel preparation 20 s; missing historical preparation error บางงานยังไม่ทราบ |
| Q15 | PRISM `load_until` เรียกซ้ำแล้ว instrumentation attach hook ซ้ำ | คง native load/identity check ทุกครั้ง แต่ attach hook ครั้งแรกเท่านั้น มี negative identity regression และ actual PRISM pass ตามมา |
| Q16 | บาง HTTP502/executor failure ไม่มี exception detail ที่ใช้วิเคราะห์ | เพิ่ม allowlisted status/class/reason/timing; ไม่เก็บ raw exceptions/secrets ต้นเหตุของ failure เก่าบางงานยัง UNKNOWN_NOT_RETAINED |
| Q17 | Predictor state flag ทำ image forwards ถูกนับเป็น warmup จนชน cap | ตรวจ actual warmup callsite และ model object identity แทน คง caps เดิม มี actual confirmation 6 warmups/213 image forwards ใน lease หนึ่ง ค่า phase split รุ่นเก่ายัง unqualified |
| Q18 | PRISM 8 งาน/lease และภายหลัง 4 งาน/lease ชน workload deadline ประมาณ 270 s | ลด existing planner 8→4→2 งาน/lease คง weights/parameters/deadlines ไม่ retry terminal jobs; นี่เป็นจำนวนงานต่อ lease ไม่ใช่ batch size ภายในโมเดล |
| Q19 | Session เดิมเหลือเวลาไม่พอ reservation+cleanup margin ทำ 175 งานยังไม่ส่ง | หยุดตาม budget gate แล้วเปิดเพียงหนึ่ง session ใหม่ตาม owner approval แยก budget คงประวัติเดิม รอบใหม่นี้ resolved 173 PASS + 1 FAILED + 1 PREMODEL รวม 175 |
| Q20 | TransportError ก่อน inference ในรอบใหม่ และ exception detail เดิมไม่ถูกเก็บ | ซ่อมช่องว่างการเก็บ diagnostic; 36 focused tests + 2 frozen checks ผ่าน แต่ต้นเหตุ transport ครั้งนั้นยังไม่ทราบ ไม่อ้างว่า transport defect แก้แล้ว |
| Q21 | Main เปิดได้แต่ AI connection ยังไม่พร้อม | **BLOCKED ด้าน interactive readiness**: finite QA API passes ไม่ยืนยัน ordinary main provider connection หรือสามโมเดลบนหน้าจอเดียวกัน |
| Q22 | Saved-result viewer ถูกปฏิเสธก่อนสร้าง process ด้วย PTY/CreateProcess; CUA ปฏิเสธ HTML file URL | **BLOCKED เฉพาะ execution/visual smoke** ไม่ใช่หลักฐานว่า HTML เสีย ไม่เปลี่ยน ACL/firewall/credentials หรือใช้ route อื่นเลี่ยง denial |
| Q23 | Stage timing เก่า/DB-only timing ไม่ได้เก็บ; warmup accounting รุ่นเก่าเชื่อถือการแบ่ง phase ไม่ได้ | เก็บ NOT_RETAINED/legacy qualification ชัดเจน ไม่ยิงซ้ำเพื่อเติมตัวเลข และไม่เรียก app-store read span ว่า DB-engine latency |
| Q24 | Mask และ export ถูกตีความเกินหลักฐานได้ | เป็น scope/acceptance gap: offline CPU post-filter เสนอซ่อน 8/65,639 raw ROI, UI subset 3, undo 7 nonempty cases; 28 UWF cases retain-all, CFP ไม่ใช้ UWF mask ไม่มี external pre-mask และยังไม่มี clinical-error reduction proof; export ข้าม 80 ภาพตาม admission ไม่ใช่เหตุให้ลด gate |
| Q25 | ชุด environment ของแต่ละ provider ต่างกัน; old package/no-code Model API เป็น contract-only | ต้องขนย้าย exact qualified environments/assets แล้วทดสอบใหม่ ไม่ใช้ one-installer หรือ presence of files เป็น runtime proof; persistent hospital service/full offline install/multiuser/backup restore ยังไม่ qualified โดยผลชุดนี้ |
| Q26 | Ad-hoc SSH source read ที่ไม่ได้ใช้ identity options ของ runtime ถูกปฏิเสธ publickey/password | ไม่ retry source read ผ่านทางอื่นหรือเปลี่ยน credentials; ช่องทาง batch ที่ owner อนุญาตยังทำงานตามสิทธิ์เดิม เหตุการณ์นี้ไม่ใช่หลักฐานว่า private inference credentials เสีย |
| Q27 | Documentation QA บน canonical workspace วันที่ 23 ต.ค. พบ broken links, duplicate sources และ PDF นอกตำแหน่งใน owner untracked/ignored presentation/archive/runtime files | Clean tracked worktree ของเอกสารผ่าน แต่ full canonical-workspace scan ยัง FAIL ต้องแยก release source จาก owner/runtime artifacts อย่างตรวจสอบได้ ห้ามลบ/ย้ายไฟล์เดิมหรือปรับ checker ให้ผ่านโดยไม่อนุมัติ; นี่เป็น packaging/workspace-hygiene gap ไม่ใช่ GPU/model failure |

ข้อเสนอ hardware เดิมวันที่ 21 ต.ค. มีฐานผล 42 งานและข้อค้างก่อน C02/B03 จึงใช้เป็นประวัติการวางแผนเท่านั้น ร่างฉบับนี้ใช้ผล 467 งานและ current local integration แทน โดยไม่เขียนทับเอกสารเดิมหรืออ้างว่าข้อค้าง persistent service เก่าได้รับการแก้แล้ว

## 4. Topology และข้อกำหนดร่วม

ใช้บทบาทเดิม: **Windows review workstation → private Model API บน Linux NVIDIA GPU host ภายในโรงพยาบาล** โดย PostgreSQL อยู่บน project-owned local service ของ workstation หรือ DB service ที่ IT อนุมัติผ่าน configuration เดิม ไม่สร้างระบบ orchestration ใหม่จากร่างนี้

- Workstation เปิด UI, เก็บ review/workspace references และ export; Model API ทำ inference โดยไม่เป็น authoritative clinical-record store ภาพต้นฉบับต้องคงเดิม
- เริ่ม inference ทีละงานบน GPU เดียว การมีหลาย browser ไม่เท่ากับรองรับหลายผู้ใช้แก้ case/workspace พร้อมกัน; centralized shared web app และ concurrent editing ต้องมี acceptance แยก
- คง RETFound สำหรับ CFP, USPEC สำหรับ UWF, PRISM สำหรับ lesion proposals โดย PRISM UWF ยัง experimental; ไม่ใช้ PRISM เป็น DR grader ไม่ auto-convert AI เป็น physician labels
- แยก raw predictions, clinician decisions, raw ROI, UI display selection และ suppression; mask ไม่บังคับยืนยันทุกภาพ ต้อง restore ได้และส่วน uncertain ต้องคงไว้
- Native model preprocessing แยกจาก external preview/post-filter ร่างนี้ไม่เสนอ pre-mask ablation หรือเปลี่ยน weights/parameters
- รับข้อมูลตาม admission/context/eye semantics เดิม จัด workspace QA ใหม่ ไม่ทับ DB/ภาพเดิม ไม่ reset volumes ไม่ silently fall back SQLite
- ใช้ private LAN/approved protected boundary, secrets server-side และ operator access ที่โรงพยาบาลอนุมัติ ไม่เปิด Model API public และไม่ส่งภาพออกนอกพื้นที่โดยอัตโนมัติ
- ให้มี receipt รายงาน invocation/source SHA, model/source/weight hashes, environment, GPU identity, stage times, error class, DB readback, cleanup และ durable request intent; ผลส่งไม่ชัดเจนต้องหยุดตรวจ ไม่ auto-retry inference
- แยก app readiness, DB readiness และ model readiness ให้เห็นชัด เมื่อ AI ใช้ไม่ได้ต้องอ่าน/บันทึก manual review ได้ตาม flow ที่ผ่าน UAT ไม่แสดง AI Ready จากแค่ health/file presence
- จัดส่งจาก clean versioned release ที่ตรวจได้ ไม่เหมารวม owner archives, local-state, runtime databases, images, weights หรือ private evidence จาก workspace; full local workspace QA ที่ FAIL ต้องรายงานแยกจาก clean tracked-source QA ที่ PASS

## 5. ร่าง hardware spec ที่เสนอ

**ทุกค่าเป็น INFERRED / TARGET_TO_QUALIFY** ไม่ได้รันทดสอบบน configuration นี้ ทั้งสองระดับยังมี execution concurrency=1 จนกว่าจะมี load test และ review isolation ที่อนุมัติ ระดับ maximum เพิ่ม headroom โดยไม่ได้เปิด worker หรือ GPU เพิ่ม

| ส่วนระบบ | Minimum: QA แบบควบคุมงาน | Maximum: กรอบบนสำหรับ QA ที่เผื่อทรัพยากร |
| --- | --- | --- |
| Linux GPU host CPU | x86-64 8 physical cores | x86-64 16 physical cores |
| GPU host RAM | 32 GB | 64 GB; เลือก ECC เมื่อ platform รองรับ |
| GPU | NVIDIA CUDA GPU หนึ่งตัว VRAM 12 GB ที่ exact runtime รองรับ | NVIDIA CUDA GPU หนึ่งตัว VRAM 24 GB ที่ exact runtime รองรับ |
| OS/runtime disk บน GPU host | NVMe SSD 1 TB | NVMe SSD 2 TB; staging/previous release แยก directory |
| Workstation CPU/RAM | 4 cores / RAM 16 GB, Windows 11 | 8 cores / RAM 32 GB, Windows 11 |
| Workstation OS/app disk | SSD 512 GB | NVMe SSD 1 TB |
| PostgreSQL | Project-owned local PostgreSQL หรือ existing IT-managed PostgreSQL ที่ qualified; ถ้าแยก VM เริ่มประเมิน 4 vCPU / 16 GB RAM / SSD 256 GB แยกจากพื้นที่ภาพ | แยก DB VM/host เพื่อการดูแลและ backup: เริ่มประเมิน 8 vCPU / 32 GB RAM / SSD 512 GB ไม่ใช่หลักฐาน multiuser capacity |
| Primary image/export storage | เริ่มประเมิน SSD usable 1 TB หรือ approved NAS ตามสูตร retention ด้านล่าง ห้ามนับความจุเดียวกันซ้ำกับ disk ระบบ | ตัวอย่าง 2×4 TB mirror ได้ usable ประมาณหนึ่ง disk ก่อน overhead หรือ approved hospital storage; ขนาดสุดท้ายตาม retention ไม่ใช่ต้องซื้อ 4 TB เสมอ |
| Backup | Storage แยก failure domain จาก primary ขนาดตาม protected data และจำนวน versions; DB backup + ภาพ/manifest/needed configuration | เพิ่ม immutable/offline copy ตามนโยบาย IT และ WAL/PITR หากต้องการ recovery target ที่ละเอียดขึ้น |
| LAN | Wired 1 GbE ภายในขอบเขตที่อนุมัติ ทดสอบ largest payload จริง | 10 GbE ระหว่าง GPU/DB/storage เมื่อใช้ storage กลางและมีเหตุผลจาก I/O measurements ไม่รับรองว่า inference เร็วขึ้นตาม bandwidth |
| Power/UPS/cooling | UPS ที่ทดสอบเวลา hold-up พอ graceful shutdown; target เริ่มประเมิน 15 นาที | UPS/managed shutdown; target เริ่มประเมิน 30 นาที เลือก PSU, GPU power, airflow ตาม vendor และ site survey |
| Execution policy | งาน inference เดียว; PRISM เริ่มที่ 2 งานต่อ finite lease ตาม planner ที่แก้แล้ว | คงงาน inference เดียวก่อนทดสอบ resident/concurrent เพิ่ม ไม่ถือ VRAM 24 GB เป็นสิทธิ์เปิดสามโมเดลพร้อมกัน |

เหตุผลที่เสนอ: GPU 11 GB เดิมแสดงว่าโมเดลรันทีละตัวได้บนชุดภาพนี้และ sampled PRISM peak อยู่ประมาณ 5.31 GiB แต่ยังไม่ได้พิสูจน์ minimum VRAM จึงเสนอ 12 GB เป็นจุดเริ่มประเมินซื้อ/นำเครื่องเดิมมาทดสอบ ส่วน 24 GB ให้ headroom ไม่ใช่คำรับรอง latency การเสนอ RAM 32/64 GB เผื่อ OS, image decode, preprocessing, service processes และ maintenance เพราะ worker RSS ไม่ครอบคลุมทั้งเครื่อง ส่วน CPU, disk และ LAN เป็น planning choices ยังไม่มี measured bottleneck profile ที่ระบุจำนวน cores/IOPS ที่จำเป็น

ถ้าโรงพยาบาลมี RTX 2080 Ti 11 GB เดิมอยู่แล้ว สามารถนำมาเป็น baseline เพื่อ UAT ได้ ไม่จำเป็นต้องซื้อใหม่เพียงเพราะตารางจัดซื้อเสนอเริ่ม 12 GB ทั้งนี้ต้องผ่าน asset/runtime/เครื่องเป้าหมาย qualification เช่นเดียวกัน

ไม่จำเป็นต้องจัด GPU ให้เครื่องแพทย์ และไม่มีหลักฐานชุดนี้ที่ทำให้ต้องเริ่มด้วย multi-GPU, GPU 48–80 GB หรือคลัสเตอร์ การเลือก GPU ต้องตรวจ architecture support ของ pinned Torch/CUDA ด้วย ไม่ใช่ดู VRAM อย่างเดียว

### Storage sizing ที่ต้องใส่ในใบประเมิน

ให้ `R` เป็นขนาด originals ที่ต้องเก็บตาม retention, `K` เป็นจำนวน full-image export snapshots ที่เก็บพร้อมกัน, `M` เป็น model/runtime/rollback assets, `D` เป็น DB/WAL, `E` เป็น derivatives/evidence และ `L` เป็น staging/logs:

```text
usable_primary >= (R + K*R + M + D + E + L) / 0.75
```

การหาร 0.75 เป็นข้อเสนอเผื่อพื้นที่ว่าง 25% ไม่ใช่ threshold ที่วัดแล้ว ใช้ actual admitted-copy plan หาก snapshots ไม่ได้คัดลอกครบทุกภาพ และรวม backup versions บน storage อีก failure domain แยกต่างหาก RAID mirror ไม่แทน backup

ตัวอย่างจากค่าเฉลี่ยชุดนี้ 10,000 ภาพจะเป็น originals ประมาณ 43.2 GB; ถ้าเก็บหนึ่ง full-copy snapshot ต้องบวกอีกราว 43.2 GB **ก่อน** DB/runtime/derivatives/headroom/backup ค่าเฉลี่ยนี้ไม่ยืนยันขนาด TIFF/DICOM หรือภาพโรงพยาบาลทุกเครื่อง จึงต้องเก็บ sample-size distribution ของโรงพยาบาลก่อนสรุป TB ที่ซื้อ

## 6. Software และ operation spec

1. ใช้ release/source identity, asset hashes และ isolated dependency inventories ของ provider ที่ผ่าน qualification เก็บ previous release สำหรับ rollback ไม่ install latest หรือเอา repository model extra ไปทับ qualified USPEC environment Configuration ที่ตรึงสำหรับ PRISM ใน batch ระบุ Torch `2.13.0+cu130`; operating guide บันทึก USPEC environment ต่างชุด จึงไม่อนุมานว่าใช้ Python environment เดียวได้ ต้องตรวจ actual inventory บนเครื่องเป้าหมายอีกครั้ง
2. OS เป้าหมายให้ประเมิน Ubuntu 22.04/24.04 LTS x86-64 กับ exact GPU/runtime; NVIDIA ระบุทั้งสองใน CUDA 13.0 support table [2] และ CUDA 13.x มี driver family ขั้นพื้นฐาน ≥580 [3] แต่ยังมี feature/PTX restrictions ต้องตรวจ exact driver/wheel/GPU และ smoke inference จริง ไม่ถือ driver number เพียงอย่างเดียวเป็น PASS
3. ใช้ PostgreSQL ตาม configuration/version ที่รับรองกับ app ห้ามเปลี่ยน major versionเป็นส่วนแถมของ QA; migration/backup restore ใช้สำเนา test database ที่ได้รับอนุมัติ ไม่ drop/resetฐานเดิม
4. จัด offline installation inventory/wheel/assets พร้อม hashes และเอกสาร rights/research restrictions ให้เจ้าของระบบพิจารณา การมีเครื่องแรงพอไม่เปลี่ยน production/clinical authorization ของโมเดล
5. มี service account/secret storage/approved private network และผู้ดูแล แต่การติดตั้ง service, ACL, firewall หรือ persistent access เป็น deployment action ที่ต้องได้รับอนุมัติต่างหาก เอกสารนี้ไม่ได้ทำการเปลี่ยนใด ๆ
6. UI ต้องแสดงงานกำลังทำ/ผลล้มเหลวอย่างชัดเจน เวลาของ queue, upload, prepare, execute, save และ readback ต้องแยกกัน ออกแบบ end-to-end feedback จาก PRISM whole-job สูงสุดที่เห็นประมาณ 109.4 s โดยไม่เอาค่า native inference deadline 30 s ไปอ้างเป็น SLA ทั้ง flow
7. ตรวจทุกชั้นของ timeout/body limit ด้วย largest admitted hospital payload และรูปแบบ encoding จริง ไม่แก้ทุก timeout เป็นค่ามาก ๆ พร้อมกัน finite batch ที่แก้มี ingress/child prepare 15 s, channel prepare 20 s, native work 30 s, workload soft270/hard300 s, parent360 s; ค่านี้เป็นประวัติ qualification ของ batch ไม่ใช่การสั่งเปลี่ยน ordinary main API contract
8. Proposed recovery targets: minimum QA RPO≤24 h / RTO≤24 h; maximum QA RPO≤15 min / RTO≤4 h เฉพาะเมื่อ backup/WAL/restore drill บนข้อมูลขนาดจริงพิสูจน์ได้ ยังเป็น TARGET_TO_QUALIFY ไม่ใช่ SLA ปัจจุบัน PostgreSQL มีวิธี SQL dump, filesystem backup และ continuous archiving/PITR ให้ IT เลือกตามแบบ [4]

## 7. Acceptance ก่อนใช้คำว่า hospital local QA ready

รายการต่อไปเป็นงานในอนาคต **NOT_RUN บนเครื่องโรงพยาบาล** ไม่ใช้ผล batch เดิมมา tick ผ่านแทน:

1. Inventory เครื่องจริง/OS/driver/venvs/assets/source hashes และสิทธิ์ข้อมูลผ่าน ระบุผู้รับผิดชอบ service, DB, backup และ source storage
2. เปิดจาก shortcut/no-code บนเครื่องเป้าหมายแล้วตรวจ app + PostgreSQL พร้อม แยก Manual Mode/AI Ready ให้ถูก ปิด–เปิด service อย่างมีหลักฐาน ไม่สรุป persistent/autostart จากการเปิด manual command ครั้งเดียว
3. ตรวจ `/health`, model discovery/capabilities และ source/weight identity ของ ordinary hospital Model API ที่ app จะใช้ ไม่แทนด้วย finite-batch ticket/gateway metadata
4. ตรวจ UI → โมเดลจริง → PostgreSQL → เปิดผลอีกครั้ง → export สำหรับ USPEC UWF, RETFound CFP และ PRISM ใน modalities ที่อนุมัติ พร้อม representative screenshots ทุกขั้น ไม่ใช้ fixtures แทน inference และไม่กล่าวว่า experimental UWF ได้ clinical qualification
5. อาจตรวจ retained results/viewer/export แบบไม่ยิงโมเดลก่อน ส่วน real inference บนเครื่องใหม่ต้องมี approval/scope/count budget ใหม่และ durable ledger ที่โยงประวัติ ไม่ replay 480 terminal jobs เดิมหรือถือสี่ slots ที่เหลือเป็นสิทธิ์ยิงซ้ำ
6. ให้ผู้ทดสอบที่ได้รับมอบหมายตรวจ context/eye, บันทึก grade/lesion ตาม flow, เปิดใหม่แล้วอ่านกลับ และตรวจ export เฉพาะ physician-confirmed labels แยก AI/UNREVIEWED; test labels ไม่ใช่ clinical gold โดยอัตโนมัติ
7. Mask preview ไม่บังคับทุกภาพ; uncertain/raw ROI/originals คงอยู่ ทดลอง suppression และ restore บนเคสที่มีรายการซ่อนจริง ตรวจ geometry/IDs และ hashes ไม่อ้างลด clinical error จากจำนวนที่ซ่อน
8. ทดสอบ largest admitted image, interrupted upload/model unavailable, stale result/identity mismatch, evidence-disk failure, DB outage และ interrupted process บน test context ที่ควบคุม ไม่มี silent success, hidden retry หรือ source overwrite
9. เปิดและตรวจ gallery/HTML ผ่านช่องทางที่อนุมัติ เก็บ actual browser screenshots เมื่อ tool access ถูกปฏิเสธต้องคง BLOCKED และให้ผู้ดูแลคืนสิทธิ์ช่องทางเดิม ไม่เปลี่ยน route เพื่อเลี่ยง denial
10. ทดลองตัดอินเทอร์เน็ต/เริ่ม service ใหม่ภายใต้แผน IT ที่อนุมัติ โดยคง LAN/DB ที่จำเป็น ตรวจไม่มี download/paid/cloud dependency ที่ไม่คาดไว้ และทำ backup restore ไป test instance ใหม่ ตรวจ SQL/results/original hashes/export manifests โดยไม่ทำลายข้อมูลเดิม
11. บันทึก p50/p95/max ของแต่ละ stage, success/failure denominators, CPU/host RAM, sampled/allocator VRAM, I/O และ LAN ด้วย workload ที่ใกล้เคียงงานจริงก่อนตั้ง SLA งาน multiuser/concurrent/model residency ต้องเป็น qualification แยก ห้ามเปิดเพิ่มเพราะเลือก maximum hardware
12. ทำ serial technical review และ owner/IT UAT ตามขอบเขต แยก clinical validation/rights review ออกจาก engineering acceptance; ไม่ใช้ผลชุดนี้อนุมัติ clinical deployment

## 8. ข้อสรุปสำหรับตัดสินใจ

เริ่มประเมิน **Linux GPU host 8 cores / RAM32 GB / GPU12 GB / NVMe1 TB + Windows review workstation RAM16 GB + PostgreSQL และ backup ที่มีผู้ดูแล** สำหรับ QA ทีละงาน หากต้องการเผื่อการดูแล/ข้อมูล ให้ประเมิน **16 cores / RAM64 GB / GPU24 GB / NVMe2 TB** พร้อมแยก DB/storage ตาม retention ก่อนเพิ่ม concurrency

สิ่งที่ต้องปิดก่อน onsite demo ครบ flow คือ ordinary main AI connection, saved-result viewer access, HTML visual smoke และ qualification บนเครื่องโรงพยาบาลจริง Hardware ที่สูงขึ้นไม่ทำให้สี่ข้อค้างนี้หายไปเอง

## 9. หลักฐานและแหล่งอ้างอิง

หลักฐาน private ที่ owner เก็บไว้ แยกจาก Git และไม่มีภาพ/weights/DB/secrets แนบมากับร่างนี้:

- `CLI_DEMO_DELIVERY_20261023.json` และ `demo-evidence-session04-20261023/FINAL_STATUS.json`: current technical scope และข้อค้าง
- `GPU_SESSION_CLOSE.json`, `EXPORT_VERIFICATION.json`, `PER_JOB_EVIDENCE.json/.csv`: request accounting, fresh readback, export, provenance และ timings
- `PRISM_POSTFILTER_MEASUREMENT.json`, `SUPPRESSION_AUDIT.json`: raw/post-filter/undo measurements
- `CLI_DEMO_OPERATIONAL_LOG_20261022.md`: เหตุการณ์สำหรับ Q01–Q27, causes, unknowns, targeted reproduction/repair receipts และ owner decisions รวม current documentation-workspace finding
- `hospital-qa-spec-draft-20261023/MEASURED_BASELINE.json`: aggregate จาก retained records; sampled resource scope และแหล่งข้อมูลพร้อม hashes

ดู [deployment topology เดิม](../operations/DEPLOYMENT.md), [Model API operations และ qualification boundaries](../operations/MODEL_SERVER.md), [configuration](../operations/CONFIGURATION.md), [dataset manifest](../reference/DATASET_MANIFEST.md) ควบคู่กัน ร่างนี้ไม่แก้ frozen behavior หรือแทน current operating guides

แหล่ง primary ที่ตรวจประกอบข้อเสนอ:

1. [NVIDIA GeForce RTX 2080 Ti specifications](https://www.nvidia.com/content/nvidiaGDC/zz/en_ZZ/geforce/graphics-cards/rtx-2080-ti.html) — memory specification; local evidence ระบุ GPU รุ่นนี้จริง
2. [NVIDIA CUDA 13.0 Linux installation support table](https://docs.nvidia.com/cuda/archive/13.0.0/cuda-installation-guide-linux/index.html) — supported OS/toolchain ไม่ใช่ app qualification
3. [NVIDIA CUDA minor-version compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html) — driver family และ compatibility caveats
4. [PostgreSQL Backup and Restore](https://www.postgresql.org/docs/18/backup.html) — backup approaches ไม่ใช่หลักฐานว่า restore/RPO/RTO ของระบบนี้ผ่านแล้ว
