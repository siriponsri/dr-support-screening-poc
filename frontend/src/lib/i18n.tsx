import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { Button, ButtonGroup } from '@chakra-ui/react';

export type Language = 'en' | 'th';

const STORAGE_KEY = 'dr-support-screening.language.v1';

/**
 * Thai body text, keyed by the English sentence. Headings and technical terms (DR grade, ICDR, ROI, PRISM,
 * Confirm Image, Worklist, Export, AI) stay English by owner decision; anything not listed shows in English.
 * Reviewed with the thai-natural-writing skill (audience: clinic staff).
 */
const THAI: Record<string, string> = {
  // Sign-in
  'Use the account your administrator gave you.': 'ใช้บัญชีที่ผู้ดูแลระบบให้ไว้',
  'Physician UX pilot for research use. Not a diagnostic device.': 'โปรแกรมทดลองใช้เพื่องานวิจัย ไม่ใช่เครื่องมือวินิจฉัยโรค',
  'Bring in a folder of CFP or UWF images, confirm the shared details once, and see which images need a closer look.':
    'นำเข้าภาพ CFP หรือ UWF ทั้งโฟลเดอร์ ยืนยันข้อมูลที่ใช้ร่วมกันครั้งเดียว แล้วดูว่าภาพไหนต้องตรวจละเอียด',
  'Each image gets a grade suggestion and possible lesion areas. Nothing becomes a label until a clinician confirms it.':
    'AI เสนอเกรดและตำแหน่งที่อาจเป็นรอยโรคให้ทุกภาพ แต่จะยังไม่เป็นผลจนกว่าแพทย์จะยืนยัน',
  'Grades and annotations are saved as you go. Export copies the images into grade folders without touching the originals.':
    'ระบบบันทึกเกรดและ annotation ให้ระหว่างทำงาน การ Export จะคัดลอกภาพไปไว้ในโฟลเดอร์ตามเกรด โดยไม่แตะภาพต้นฉบับ',
  // Today
  'Your review work at a glance': 'ภาพรวมงานตรวจภาพของคุณ',
  'AI result, awaiting review': 'มีผล AI แล้ว รอตรวจ',
  'Confirmed, no AI result yet': 'ยืนยันภาพแล้ว ยังไม่มีผล AI',
  'Grade and lesions confirmed': 'ยืนยันเกรดและรอยโรคแล้ว',
  'Confirm the image first': 'ต้องยืนยันภาพก่อน',
  'Continue reviewing': 'ตรวจภาพถัดไป',
  'Import or confirm images': 'นำเข้าหรือยืนยันภาพ',
  'The AI server runs from 06:00 to 22:00, Thailand time.': 'AI server เปิดใช้ได้ 06:00 ถึง 22:00 น. ตามเวลาประเทศไทย',
  'Outside AI hours (06:00 to 22:00, Thailand time). Review and export still work.':
    'ตอนนี้อยู่นอกเวลาใช้ AI (06:00 ถึง 22:00 น.) แต่ยังตรวจภาพและ Export ได้ตามปกติ',
  'AI status is shown at the top right.': 'ดูสถานะ AI ได้ที่มุมขวาบน',
  'No AI batch yet. Start one from the Worklist after confirming images.': 'ยังไม่มี AI batch เริ่มได้จากหน้า Worklist หลังยืนยันภาพแล้ว',
  // Review
  'AI is a suggestion only. You can always review without it.': 'ผล AI เป็นแค่คำแนะนำ ตรวจภาพได้เสมอแม้ไม่มี AI',
  'You can review this image without AI.': 'ตรวจภาพนี้ได้โดยไม่ต้องใช้ AI',
  'AI suggests a grade. You confirm or correct it.': 'AI เสนอเกรด คุณเป็นคนยืนยันหรือแก้ไข',
  // Section descriptions and page subtitles (translated where they are shown)
  "AI output is optional evidence; this page records the clinician's final grade.": 'ผล AI เป็นข้อมูลประกอบเท่านั้น หน้านี้บันทึกเกรดสุดท้ายที่แพทย์ยืนยัน',
  'AI results and clinician decisions are kept separately; open a case to see its full stored record.': 'ระบบเก็บผล AI แยกจากการตัดสินของแพทย์ เปิดแต่ละเคสเพื่อดูข้อมูลที่เก็บไว้ทั้งหมด',
  'Applies to new and changed passwords and to every sign-in.': 'ใช้กับรหัสผ่านใหม่ รหัสที่เปลี่ยน และการ sign-in ทุกครั้ง',
  'Automatic same-patient, same-eye comparison uses verified private linkage and sequence metadata.': 'การเทียบภาพของผู้ป่วยคนเดียวกันและตาข้างเดียวกันใช้ข้อมูลเชื่อมโยงและลำดับภาพที่ตรวจสอบแล้ว',
  'Bounded lesion suggestions remain model evidence and do not mean that an empty result is negative.': 'ตำแหน่งรอยโรคที่ AI เสนอเป็นแค่ข้อมูลจากโมเดล ถ้า AI ไม่พบรอยโรค ไม่ได้แปลว่าไม่มีรอยโรค',
  'Capability metadata and unavailable/deferred states are shown honestly; no registry state implies clinical qualification.': 'แสดงความสามารถของโมเดลและสถานะที่ยังใช้ไม่ได้ตามจริง สถานะในรายการไม่ได้หมายความว่าผ่านการรับรองทางคลินิก',
  'Choose a returned case to inspect its actual inference metadata and results.': 'เลือกเคสเพื่อดูข้อมูลการประมวลผลและผลลัพธ์จริงของโมเดล',
  'Choose an image from the Worklist to open Review.': 'เลือกภาพจาก Worklist เพื่อเปิดหน้า Review',
  'Choose the final DR grade, then confirm it.': 'เลือก DR grade สุดท้าย แล้วกดยืนยัน',
  'Choose where AI analysis runs. Images may leave the hospital only when they are public or consented.': 'เลือกว่าจะให้ AI ประมวลผลที่ไหน ภาพจะออกนอกโรงพยาบาลได้เฉพาะภาพสาธารณะหรือภาพที่ได้รับ consent',
  'Copy original image bytes into a new canonical snapshot. Originals and earlier snapshots are never moved or updated.': 'คัดลอกภาพต้นฉบับเป็น snapshot ชุดใหม่ ระบบไม่ย้ายหรือแก้ไขภาพต้นฉบับและ snapshot เดิม',
  'Fill in what you have; only the screening result is needed to sign.': 'กรอกเท่าที่มีข้อมูล การลงนามต้องมีแค่ผลคัดกรอง',
  'Inspect the image and record only the findings you choose to keep.': 'ตรวจภาพและบันทึกเฉพาะสิ่งที่คุณต้องการเก็บไว้',
  'Metadata-only canonical snapshots do not copy images. The older grouped-image export updates a shared folder; use Grading-folder snapshot for a new immutable copy.': 'Snapshot แบบ metadata ไม่คัดลอกภาพ ส่วน Export แบบเดิมจะเขียนลงโฟลเดอร์เดียวกันซ้ำ ถ้าต้องการชุดใหม่ที่ไม่ถูกแก้ ให้ใช้ Grading-folder snapshot',
  'Open an image to grade it. Your grade is the reference; the AI suggestion stays hidden until you save it.': 'เปิดภาพเพื่อให้เกรด เกรดของคุณคือคำตอบอ้างอิง ระบบจะซ่อนผล AI จนกว่าคุณจะบันทึกเกรด',
  'Optional diagnostics for IT and supervised usability studies. Off by default; memory only until this tab closes or you clear it.': 'เครื่องมือตรวจสอบสำหรับ IT และการทดสอบการใช้งาน ปิดไว้เป็นค่าเริ่มต้น ข้อมูลอยู่ในหน่วยความจำจนกว่าจะปิดแท็บหรือกดล้าง',
  'Optional provider-neutral connection for a hospital LAN GPU server or local GPU API.': 'ตั้งค่าการเชื่อมต่อ GPU server ในเครือข่ายโรงพยาบาลหรือ GPU API ในเครื่อง (ไม่บังคับ)',
  'Persisted in the existing case store with revision history.': 'บันทึกในฐานข้อมูลเคสพร้อมประวัติการแก้ไข',
  'Raw model scores are research evidence, not calibrated clinical probabilities.': 'คะแนนดิบของโมเดลเป็นข้อมูลวิจัย ไม่ใช่ความน่าจะเป็นทางคลินิกที่ผ่านการปรับเทียบ',
  'Read-only evidence for this case. Hashes identify the source and exact analysis bytes; counts do not establish accuracy.': 'ข้อมูลอ่านอย่างเดียวของเคสนี้ ค่า hash ระบุภาพต้นฉบับและภาพที่ใช้วิเคราะห์ ตัวเลขนับไม่ได้บอกความแม่นยำ',
  'Read-only provenance for the source, derived representation, mapping, and model-domain state.': 'ที่มาของภาพต้นฉบับ ภาพที่ใช้วิเคราะห์ การแปลงพิกัด และขอบเขตของโมเดล (อ่านอย่างเดียว)',
  'Review admitted images, resolve patient and eye identity, and keep AI assistance separate from the clinician decision.': 'ตรวจภาพที่นำเข้า ยืนยันผู้ป่วยและตาข้างที่ถ่าย โดยแยกผล AI ออกจากการตัดสินของแพทย์',
  'Set a workstation default for new review records. It is editable and is not an authenticated identity.': 'ตั้งชื่อผู้ตรวจเริ่มต้นของเครื่องนี้ แก้ไขได้ และไม่ใช่การยืนยันตัวตน',
  'Shown only after your own grade is saved. Your saved grade stays as it is.': 'แสดงหลังจากคุณบันทึกเกรดแล้วเท่านั้น เกรดที่บันทึกไว้จะไม่เปลี่ยน',
  'The confirmed grade is read-only. Reopen it only if the grade must change.': 'เกรดที่ยืนยันแล้วแก้ไม่ได้ เปิดใหม่เฉพาะเมื่อจำเป็นต้องเปลี่ยนเกรด',
  'Use filters to inspect bounded pages of persisted review records. No review actions are available here.': 'ใช้ตัวกรองเพื่อดูข้อมูลการตรวจที่บันทึกไว้ทีละหน้า หน้านี้ใช้ดูอย่างเดียว',
  'You choose the result. The app does not decide the referral.': 'คุณเป็นคนเลือกผล ระบบไม่ได้ตัดสินการส่งต่อแทน',
  'Your grade is the reference. Only the grade and gradability are needed.': 'เกรดของคุณคือคำตอบอ้างอิง ต้องกรอกแค่เกรดและภาพอ่านได้หรือไม่',
  'Retinal images for clinician review': 'ภาพจอประสาทตาที่รอแพทย์ตรวจ',
  'Manage retinal imaging workspaces': 'จัดการ Workspace ของภาพจอประสาทตา',
  'Check the image and the AI result, then confirm': 'ตรวจภาพและผล AI แล้วกดยืนยัน',
  'Create explicit human annotations in original image space': 'วาด annotation บนพิกัดของภาพต้นฉบับ',
  'Research labels by the ophthalmologist': 'ข้อมูลวิจัยที่จักษุแพทย์เป็นผู้ให้',
  'The grader chooses Refer or Not refer; a physician signs': 'ผู้ให้เกรดเลือก Refer หรือ Not refer แล้วแพทย์ลงนาม',
  'Human sign-off and review record': 'การลงนามของแพทย์และบันทึกการตรวจ',
  'Provider readiness, provenance, limitations': 'ความพร้อม ที่มา และข้อจำกัดของโมเดล',
  'Workspace, runtime, and clinician preferences': 'ตั้งค่า Workspace ระบบ และค่าที่ผู้ใช้เลือก',
  'Clinician review workspace': 'พื้นที่ทำงานตรวจภาพของแพทย์',
  // Admin
  'Accounts and stored data': 'บัญชีผู้ใช้และข้อมูลที่เก็บไว้',
  'Give the person a temporary password; the app asks them to choose their own at first sign-in.':
    'ตั้งรหัสผ่านชั่วคราวให้ผู้ใช้ เมื่อเข้าใช้ครั้งแรก ระบบจะให้ตั้งรหัสผ่านของตัวเอง',
  'Disabling an account signs that person out at once.': 'เมื่อปิดบัญชี ระบบจะพาผู้ใช้คนนั้นออกจากระบบทันที',
  'Only an administrator can open this page.': 'หน้านี้เปิดได้เฉพาะผู้ดูแลระบบ',
};

function storedLanguage(): Language {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'th' ? 'th' : 'en';
  } catch {
    return 'en';
  }
}

interface LanguageState { language: Language; setLanguage: (language: Language) => void }

const LanguageContext = createContext<LanguageState>({ language: 'en', setLanguage: () => undefined });

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(storedLanguage);
  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    try { window.localStorage.setItem(STORAGE_KEY, next); } catch { /* A per-viewer preference only. */ }
  }, []);
  const value = useMemo(() => ({ language, setLanguage }), [language, setLanguage]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageState {
  return useContext(LanguageContext);
}

/** `t(english)`: the Thai body text when Thai is chosen and a translation exists, else the English. */
export function useT(): (english: string) => string {
  const { language } = useContext(LanguageContext);
  return useCallback((english: string) => (language === 'th' ? THAI[english] ?? english : english), [language]);
}

/** EN / TH switch for the header and the sign-in page. */
export function LanguageSwitch() {
  const { language, setLanguage } = useLanguage();
  return (
    <ButtonGroup size="xs" isAttached variant="outline" role="group" aria-label="Language">
      {(['en', 'th'] as const).map((code) => (
        <Button key={code} aria-pressed={language === code} variant={language === code ? 'solid' : 'outline'}
          onClick={() => setLanguage(code)}>{code.toUpperCase()}</Button>
      ))}
    </ButtonGroup>
  );
}
