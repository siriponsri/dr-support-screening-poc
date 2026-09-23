import { useLayoutEffect, useRef, useState } from 'react';
import { Box, Button, CloseButton, FormControl, FormLabel, HStack, Select, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord, LesionLabel } from '@/lib/api';
import type { ViewerOverlayContext, ViewerRect } from './RetinalCanvas';
import { aiEvidenceForLesion, type DisplayedLesion } from './lesionPresentation';

export const ROI_LABEL_OPTIONS: Array<{ value: LesionLabel; label: string }> = [
  { value: 'MICROANEURYSM', label: 'Microaneurysm' },
  { value: 'HEMORRHAGE', label: 'Hemorrhage' },
  { value: 'HARD_EXUDATE', label: 'Hard exudate' },
  { value: 'SOFT_EXUDATE', label: 'Soft exudate' },
];

export function roiLabelText(label: string | null | undefined): string {
  return ROI_LABEL_OPTIONS.find((option) => option.value === label)?.label ?? 'Unknown class';
}

export type RoiPlacement = 'right' | 'left' | 'below' | 'above' | 'docked';

export interface RoiPopoverPosition {
  left: number;
  top: number;
  placement: RoiPlacement;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function overlaps(a: ViewerRect, b: ViewerRect) {
  return a.left < b.left + b.width && a.left + a.width > b.left && a.top < b.top + b.height && a.top + a.height > b.top;
}

/**
 * Viewport collision placement for the selected-ROI card. Prefer a side that
 * keeps the ROI uncovered; otherwise dock the card to the viewport corner
 * farthest from the ROI so the selected region stays visible.
 */
export function placeRoiPopover(
  roi: ViewerRect,
  viewport: { width: number; height: number },
  card: { width: number; height: number },
  gap = 12,
  margin = 8,
): RoiPopoverPosition {
  const maxLeft = Math.max(margin, viewport.width - card.width - margin);
  const maxTop = Math.max(margin, viewport.height - card.height - margin);
  const verticalTop = clamp(roi.top + roi.height / 2 - card.height / 2, margin, maxTop);
  const horizontalLeft = clamp(roi.left + roi.width / 2 - card.width / 2, margin, maxLeft);
  const roiVisible = roi.left + roi.width > 0 && roi.top + roi.height > 0
    && roi.left < viewport.width && roi.top < viewport.height;
  const candidates: RoiPopoverPosition[] = roiVisible ? [
    { placement: 'right', left: roi.left + roi.width + gap, top: verticalTop },
    { placement: 'left', left: roi.left - gap - card.width, top: verticalTop },
    { placement: 'below', left: horizontalLeft, top: roi.top + roi.height + gap },
    { placement: 'above', left: horizontalLeft, top: roi.top - gap - card.height },
  ] : [];
  for (const candidate of candidates) {
    const box = { left: candidate.left, top: candidate.top, width: card.width, height: card.height };
    const inside = box.left >= margin && box.top >= margin
      && box.left + box.width <= viewport.width - margin
      && box.top + box.height <= viewport.height - margin;
    if (inside && !overlaps(box, roi)) return candidate;
  }
  const centerX = roi.left + roi.width / 2;
  const centerY = roi.top + roi.height / 2;
  const corners = [
    { left: margin, top: margin },
    { left: maxLeft, top: margin },
    { left: margin, top: maxTop },
    { left: maxLeft, top: maxTop },
  ];
  const distance = (corner: { left: number; top: number }) => Math.hypot(
    corner.left + card.width / 2 - centerX,
    corner.top + card.height / 2 - centerY,
  );
  const best = corners.reduce((winner, corner) => (distance(corner) > distance(winner) ? corner : winner), corners[0]);
  return { ...best, placement: 'docked' };
}

interface AiRoiPopoverProps {
  item: CaseRecord;
  lesion: DisplayedLesion;
  context: ViewerOverlayContext;
  label: LesionLabel;
  rectangle: [number, number, number, number];
  geometryChanged: boolean;
  saving: boolean;
  error: string | null;
  onLabelChange: (label: LesionLabel) => void;
  onConfirm: () => void;
  onRemove: () => void;
  onClose: () => void;
}

const CARD_WIDTH = 292;

/**
 * Single in-place card for the selected AI ROI. It never shows the AI score as
 * belonging to a clinician-changed class or box.
 */
export function AiRoiPopover({
  item,
  lesion,
  context,
  label,
  rectangle,
  geometryChanged,
  saving,
  error,
  onLabelChange,
  onConfirm,
  onRemove,
  onClose,
}: AiRoiPopoverProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [cardHeight, setCardHeight] = useState(280);
  useLayoutEffect(() => {
    const height = cardRef.current?.offsetHeight;
    if (height && Math.abs(height - cardHeight) > 1) setCardHeight(height);
  });

  const evidence = aiEvidenceForLesion(item, lesion.detection_id);
  const aiLabel = (lesion.originalLabel ?? evidence?.original_label ?? lesion.canonical_label) as string;
  const aiScore = evidence?.original_score ?? lesion.originalScore ?? lesion.score;
  const classChanged = label !== aiLabel;
  const corrected = classChanged || geometryChanged || lesion.reviewState === 'CLINICIAN_CORRECTED';
  const modelName = item.lesion?.model_id === 'prism-dr-5fold' || !item.lesion?.model_id ? 'PRISM-DR' : item.lesion.model_id;

  const roi = context.toViewport(rectangle);
  const width = Math.min(CARD_WIDTH, Math.max(220, context.viewport.width - 16));
  const position = placeRoiPopover(roi, context.viewport, { width, height: cardHeight });

  return (
    <Box
      ref={cardRef}
      role="dialog"
      aria-label="AI suggestion"
      data-roi-popover-placement={position.placement}
      position="absolute"
      zIndex={3}
      left={`${position.left}px`}
      top={`${position.top}px`}
      w={`${width}px`}
      bg="surface.panel"
      color="text.primary"
      borderWidth="1px"
      borderColor="border.default"
      borderRadius="md"
      boxShadow="0 8px 24px rgb(15 23 42 / 0.18)"
      p={3}
      cursor="default"
      onPointerDown={(event) => event.stopPropagation()}
      onWheel={(event) => event.stopPropagation()}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <Stack spacing={2}>
        <HStack justify="space-between" align="center">
          <Text fontWeight="semibold" fontSize="sm">AI suggestion</Text>
          <CloseButton size="sm" aria-label="Close AI suggestion" onClick={onClose} isDisabled={saving} />
        </HStack>
        <FormControl>
          <FormLabel htmlFor="ai-roi-class" fontSize="xs" mb={1}>Lesion class</FormLabel>
          <Select id="ai-roi-class" size="sm" value={label} onChange={(event) => onLabelChange(event.target.value as LesionLabel)} isDisabled={saving}>
            {ROI_LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </Select>
        </FormControl>
        {corrected ? (
          <Text fontSize="sm" data-testid="roi-score-line"><strong>Model score:</strong> {aiScore.toFixed(2)} <Text as="span" color="text.secondary">for AI class {roiLabelText(aiLabel)}</Text></Text>
        ) : (
          <Text fontSize="sm" data-testid="roi-score-line"><strong>Model score:</strong> {aiScore.toFixed(2)}</Text>
        )}
        <Text fontSize="sm"><strong>Model:</strong> {modelName}</Text>
        <Text fontSize="xs" color="text.secondary">
          {corrected
            ? 'Your correction is saved as a human annotation without a model score. The original AI suggestion stays in the record.'
            : 'Model score, not a clinical probability. Drag or resize the box to correct it.'}
        </Text>
        {error && <Text role="alert" fontSize="sm" color="status.danger">{error}</Text>}
        <HStack spacing={2} pt={1}>
          <Button size="sm" variant="solid" onClick={onConfirm} isLoading={saving}>Confirm</Button>
          <Button size="sm" variant="danger" onClick={onRemove} isDisabled={saving}>Remove</Button>
          <Button size="sm" variant="ghost" onClick={onClose} isDisabled={saving}>Close</Button>
        </HStack>
      </Stack>
    </Box>
  );
}
