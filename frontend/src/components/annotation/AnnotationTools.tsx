/** Annotation editor toolbar pieces: tool buttons, the More tools popup, ROI correction box and draw preview. */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Box, Button, HStack } from '@chakra-ui/react';
import type { RectangleResizeHandle } from '@/components/review/RetinalCanvas';
import type { AnnotationGeometry, LesionLabel } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { ChevronDown, Circle, CircleDot, Pentagon } from '@/lib/icons';
import { HANDLE_CURSORS, handlePoint, ROI_HANDLES, type RoiRectangle, type Tool } from './annotationGeometry';

export const TOOL_LABELS: Record<Tool, string> = {
  select: 'Select',
  rectangle: 'Box',
  polygon: 'Polygon',
  point: 'Point',
  circle: 'Circle',
};

export const TOOL_GUIDANCE: Record<Tool, string> = {
  select: 'Select a finding to edit.',
  rectangle: 'Drag to draw a box.',
  polygon: 'Click points; double-click to finish.',
  point: 'Click to place a point.',
  circle: 'Drag to size a circle.',
};

export const LABEL_OPTIONS: Array<{ value: LesionLabel; label: string }> = [
  { value: 'MICROANEURYSM', label: 'Microaneurysm' },
  { value: 'HEMORRHAGE', label: 'Hemorrhage' },
  { value: 'HARD_EXUDATE', label: 'Hard exudate' },
  { value: 'SOFT_EXUDATE', label: 'Soft exudate' },
];

export function RoiCorrectionBox({ rect, scale }: { rect: RoiRectangle; scale: number }) {
  const [x1, y1, x2, y2] = rect;
  const safeScale = Math.max(scale, 0.01);
  const screenSize = Math.min(x2 - x1, y2 - y1) * safeScale;
  // Small lesions keep only corner handles, sized so the lesion stays visible.
  const compact = screenSize < 44;
  const size = (compact ? 7 : 10) / safeScale;
  const handles = compact ? ROI_HANDLES.filter((handle) => handle.length === 2) : ROI_HANDLES;
  const offset = compact ? size / 2 : 0;
  return (
    <g data-roi-correction="true">
      <rect
        data-roi-edit="body"
        x={x1}
        y={y1}
        width={x2 - x1}
        height={y2 - y1}
        fill="var(--chakra-colors-text-primary)"
        fillOpacity={0.08}
        stroke="var(--chakra-colors-text-primary)"
        strokeWidth={2.5}
        vectorEffect="non-scaling-stroke"
        style={{ cursor: 'move' }}
      />
      {handles.map((handle) => {
        const [hx, hy] = handlePoint(rect, handle);
        // Compact corner handles sit just outside the box instead of over the lesion.
        const x = hx + (handle.includes('w') ? -offset : handle.includes('e') ? offset : 0);
        const y = hy + (handle.includes('n') ? -offset : handle.includes('s') ? offset : 0);
        return (
          <rect
            key={handle}
            data-roi-edit="handle"
            data-roi-handle={handle}
            x={x - size / 2}
            y={y - size / 2}
            width={size}
            height={size}
            fill="var(--chakra-colors-text-inverse)"
            stroke="var(--chakra-colors-text-primary)"
            strokeWidth={1.5}
            vectorEffect="non-scaling-stroke"
            style={{ cursor: HANDLE_CURSORS[handle] }}
          />
        );
      })}
    </g>
  );
}

export function previewShape(preview: { type: Tool; geometry: AnnotationGeometry } | null) {
  if (!preview) return null;
  const { type, geometry } = preview;
  const color = 'var(--chakra-colors-text-primary)';
  if (type === 'rectangle' && 'width' in geometry) {
    return <rect x={geometry.x} y={geometry.y} width={geometry.width} height={geometry.height} fill={color} fillOpacity={0.1} stroke={color} strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />;
  }
  if (type === 'circle' && 'radius' in geometry) {
    return <circle cx={geometry.cx} cy={geometry.cy} r={geometry.radius} fill={color} fillOpacity={0.1} stroke={color} strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />;
  }
  if (type === 'point' && 'x' in geometry) {
    return <circle cx={geometry.x} cy={geometry.y} r={8} fill={color} fillOpacity={0.2} stroke={color} strokeWidth={3} vectorEffect="non-scaling-stroke" />;
  }
  if (type === 'polygon' && 'points' in geometry) {
    return <polyline points={geometry.points.map((point) => point.join(',')).join(' ')} fill={color} fillOpacity={0.1} stroke={color} strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />;
  }
  return null;
}

export function ToolButton({ active, onClick, children, ariaLabel, isDisabled = false }: { active?: boolean; onClick: () => void; children: React.ReactNode; ariaLabel?: string; isDisabled?: boolean }) {
  return <Button size="sm" variant={active ? 'secondary' : 'outline'} onClick={onClick} aria-label={ariaLabel} aria-pressed={active} isDisabled={isDisabled}>{children}</Button>;
}

export function MoreToolsPopover({
  open,
  onOpenChange,
  tool,
  onToolChange,
  onActivate,
  disabled,
  inspectorActive,
  fullscreen = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tool: Tool;
  onToolChange: (tool: Tool) => void;
  onActivate: (tool: Tool) => void;
  disabled: boolean;
  inspectorActive: boolean;
  fullscreen?: boolean;
}) {
  const t = useT();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const [popupPosition, setPopupPosition] = useState({ top: 12, left: 12 });
  const close = useCallback((restoreFocus = true) => {
    onOpenChange(false);
    if (restoreFocus) window.setTimeout(() => triggerRef.current?.focus(), 0);
  }, [onOpenChange]);
  const choose = (nextTool: Tool) => {
    onActivate(nextTool);
    onToolChange(nextTool);
    close();
  };

  const popupId = fullscreen ? 'fullscreen-more-tools' : 'annotation-more-tools';
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDownCapture = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      close();
    };
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !containerRef.current?.contains(event.target) && !popupRef.current?.contains(event.target)) {
        const clickedControl = event.target instanceof Element
          && Boolean(event.target.closest('button, a, input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="combobox"], [role="menuitem"], [role="option"], [role="switch"], [role="tab"], [contenteditable="true"]'));
        close(!clickedControl);
      }
    };
    // Capture before Chakra's Modal handler so Escape only closes this popup.
    document.addEventListener('keydown', onKeyDownCapture, true);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDownCapture, true);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [close, open]);

  useEffect(() => {
    if (!open) return undefined;
    const frame = window.requestAnimationFrame(() => {
      popupRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return undefined;
    const updatePlacement = () => {
      const trigger = triggerRef.current?.getBoundingClientRect();
      const popup = popupRef.current;
      if (!trigger || !popup) return;
      const popupRect = popup.getBoundingClientRect();
      const popupWidth = popupRect.width || 240;
      const popupHeight = popupRect.height || 56;
      const maxLeft = Math.max(12, window.innerWidth - popupWidth - 12);
      const left = Math.min(Math.max(12, trigger.left), maxLeft);
      const below = trigger.bottom + 6;
      const above = trigger.top - popupHeight - 6;
      const preferredTop = below + popupHeight > window.innerHeight - 12 && above >= 12 ? above : below;
      const maxTop = Math.max(12, window.innerHeight - popupHeight - 12);
      const top = Math.min(Math.max(12, preferredTop), maxTop);
      setPopupPosition({ top, left });
    };
    const frame = window.requestAnimationFrame(updatePlacement);
    window.addEventListener('resize', updatePlacement);
    window.addEventListener('scroll', updatePlacement, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', updatePlacement);
      window.removeEventListener('scroll', updatePlacement, true);
    };
  }, [open]);

  return (
    <Box ref={containerRef} position="relative" display="inline-flex">
      <Button
        ref={triggerRef}
        size="sm"
        variant="outline"
        rightIcon={<ChevronDown size={14} aria-hidden="true" />}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? popupId : undefined}
        onClick={() => onOpenChange(!open)}
        isDisabled={disabled}
      >
        {t('More tools')}
      </Button>
      {/* Keep the popup in the owning Modal subtree so focus lock remains local. */}
      {open && (
        <Box
          id={popupId}
          ref={popupRef}
          role="dialog"
          aria-label={t('Annotation tools')}
          position="fixed"
          top={`${popupPosition.top}px`}
          left={`${popupPosition.left}px`}
          width="max-content"
          maxW="calc(100vw - 24px)"
          maxH="calc(100vh - 24px)"
          overflowY="auto"
          bg="surface.panel"
          borderWidth="1px"
          borderColor="border.default"
          borderRadius="md"
          boxShadow="md"
          zIndex="popover"
          p={2}
        >
          <HStack spacing={2} flexWrap="wrap">
            <ToolButton ariaLabel={fullscreen ? 'Polygon tool' : 'Polygon'} active={tool === 'polygon'} onClick={() => choose('polygon')} isDisabled={inspectorActive || disabled}>
              <Pentagon size={14} aria-hidden="true" /><Box>Polygon</Box>
            </ToolButton>
            <ToolButton ariaLabel={fullscreen ? 'Point tool' : 'Point'} active={tool === 'point'} onClick={() => choose('point')} isDisabled={inspectorActive || disabled}>
              <CircleDot size={14} aria-hidden="true" /><Box>Point</Box>
            </ToolButton>
            <ToolButton ariaLabel={fullscreen ? 'Circle tool' : 'Circle'} active={tool === 'circle'} onClick={() => choose('circle')} isDisabled={inspectorActive || disabled}>
              <Circle size={14} aria-hidden="true" /><Box>Circle</Box>
            </ToolButton>
          </HStack>
        </Box>
      )}
    </Box>
  );
}
