import { useEffect, type MutableRefObject } from 'react';
import type { CaseRecord, HumanAnnotation } from '@/lib/api';

/** Autosave delay for the annotation draft (unchanged: 900 ms after the last edit). */
export const ANNOTATION_AUTOSAVE_DELAY_MS = 900;

export type DraftStatus = 'saved' | 'unsaved' | 'saving' | 'failed';

export interface AnnotationDraftOptions {
  item: CaseRecord | null;
  draft: HumanAnnotation[];
  draftStatus: DraftStatus;
  reviewer: string;
  completing: boolean;
  saving: boolean;
  roiSaving: boolean;
  /** Saves the current draft; `withinAction` lets an ROI decision or Finish save while it holds the action lock. */
  persistDraft: (withinAction?: boolean) => Promise<CaseRecord | null>;
  skipAutosaveRef: MutableRefObject<boolean>;
  actionBusyRef: MutableRefObject<boolean>;
  interactionRef: MutableRefObject<boolean>;
  savingRef: MutableRefObject<boolean>;
}

/**
 * Draft autosave and flush for the annotation editor.
 *
 * - Autosave: 900 ms after the last change, only while nothing else is saving, no ROI decision or Finish is
 *   running, no drag is in progress and a reviewer name is set. The first run after a case load is skipped.
 * - `flushedCase`: ROI decisions and Finish call it first, so the pending draft is saved before them and the
 *   revisions never race.
 * - Leaving the page with unsaved, saving or failed changes asks the browser to confirm.
 *
 * Call it at the same place the page used to declare these effects so the effect order stays the same.
 */
export function useAnnotationDraft({
  item,
  draft,
  draftStatus,
  reviewer,
  completing,
  saving,
  roiSaving,
  persistDraft,
  skipAutosaveRef,
  actionBusyRef,
  interactionRef,
  savingRef,
}: AnnotationDraftOptions) {
  /** Flush any pending draft so ROI decisions never race the autosave revision. */
  const flushedCase = async (): Promise<CaseRecord | null> => {
    if (!item) return null;
    if (draftStatus === 'saved') return item;
    return persistDraft(true);
  };

  useEffect(() => {
    if (skipAutosaveRef.current) {
      skipAutosaveRef.current = false;
      return;
    }
    if (completing || saving || roiSaving || actionBusyRef.current || draftStatus !== 'unsaved' || interactionRef.current || !reviewer.trim()) return;
    const timer = window.setTimeout(() => { void persistDraft(); }, ANNOTATION_AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [completing, saving, roiSaving, draft, draftStatus, reviewer]);

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (actionBusyRef.current || savingRef.current || draftStatus === 'unsaved' || draftStatus === 'saving' || draftStatus === 'failed') {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [draftStatus]);

  return { flushedCase };
}
