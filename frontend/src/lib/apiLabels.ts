/** Plain-language labels derived from API values. */

export const DR_GRADE_LABELS: Record<number, string> = {
  0: 'No apparent DR',
  1: 'Mild NPDR',
  2: 'Moderate NPDR',
  3: 'Severe NPDR',
  4: 'Proliferative DR (PDR)',
};

export function drGradeLabel(grade: number | null | undefined): string | null {
  return grade == null ? null : DR_GRADE_LABELS[grade] ?? null;
}

/** Server refusals that are written for clinicians and may be shown as-is. */
export const PLAIN_EXPORT_REFUSALS = ['Hospital records can be exported only to a local folder'];

/** The server's plain export refusal, or null so the caller keeps its generic message. */
export function plainExportRefusal(error: unknown): string | null {
  const message = error instanceof Error ? error.message : '';
  return PLAIN_EXPORT_REFUSALS.some((prefix) => message.startsWith(prefix)) ? message : null;
}
