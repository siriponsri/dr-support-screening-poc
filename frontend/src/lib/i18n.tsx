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
