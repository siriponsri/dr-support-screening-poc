/** Annotation geometry in original-image pixels: pointer mapping, move, resize and ROI box edits. */
import type { PointerEvent as ReactPointerEvent } from 'react';
import type { RectangleResizeHandle } from '@/components/review/RetinalCanvas';
import type { AnnotationGeometry, AnnotationType, CaseRecord, HumanAnnotation, LesionLabel } from '@/lib/api';

export type Tool = 'select' | 'rectangle' | 'polygon' | 'point' | 'circle';

export type Point = [number, number];

export const MIN_RESIZE_SIZE = 4;

export function pointFromEvent(event: ReactPointerEvent<SVGSVGElement>, item: Pick<CaseRecord, 'width' | 'height'>): Point {
  const bounds = event.currentTarget.getBoundingClientRect();
  // The image and SVG share the transformed stage, so the transformed bounds
  // map pointer coordinates back to the original-image viewBox.
  const clientX = Number.isFinite(event.clientX) ? event.clientX : bounds.left;
  const clientY = Number.isFinite(event.clientY) ? event.clientY : bounds.top;
  return [
    Math.max(0, Math.min(item.width, ((clientX - bounds.left) / Math.max(bounds.width, 1)) * item.width)),
    Math.max(0, Math.min(item.height, ((clientY - bounds.top) / Math.max(bounds.height, 1)) * item.height)),
  ];
}

export function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function boundedDelta(delta: Point, minX: number, maxX: number, minY: number, maxY: number): Point {
  return [clamp(delta[0], minX, maxX), clamp(delta[1], minY, maxY)];
}

export function translateAnnotationGeometry(
  annotation: HumanAnnotation,
  delta: Point,
  item: Pick<CaseRecord, 'width' | 'height'>,
): AnnotationGeometry {
  const geometry = annotation.geometry;
  if (annotation.type === 'rectangle' && 'width' in geometry) {
    const [dx, dy] = boundedDelta(delta, -geometry.x, item.width - geometry.x - geometry.width, -geometry.y, item.height - geometry.y - geometry.height);
    return { ...geometry, x: geometry.x + dx, y: geometry.y + dy };
  }
  if (annotation.type === 'polygon' && 'points' in geometry) {
    const minX = Math.min(...geometry.points.map(([x]) => x));
    const maxX = Math.max(...geometry.points.map(([x]) => x));
    const minY = Math.min(...geometry.points.map(([, y]) => y));
    const maxY = Math.max(...geometry.points.map(([, y]) => y));
    const [dx, dy] = boundedDelta(delta, -minX, item.width - maxX, -minY, item.height - maxY);
    return { points: geometry.points.map(([x, y]) => [x + dx, y + dy]) };
  }
  if (annotation.type === 'point' && 'x' in geometry && !('width' in geometry)) {
    const [dx, dy] = boundedDelta(delta, -geometry.x, item.width - geometry.x, -geometry.y, item.height - geometry.y);
    return { x: geometry.x + dx, y: geometry.y + dy };
  }
  if (annotation.type === 'circle' && 'radius' in geometry) {
    const [dx, dy] = boundedDelta(delta, -geometry.cx + geometry.radius, item.width - geometry.cx - geometry.radius, -geometry.cy + geometry.radius, item.height - geometry.cy - geometry.radius);
    return { ...geometry, cx: geometry.cx + dx, cy: geometry.cy + dy };
  }
  return geometry;
}

export function resizeRectangleGeometry(
  annotation: HumanAnnotation,
  handle: RectangleResizeHandle,
  point: Point,
  item: Pick<CaseRecord, 'width' | 'height'>,
): AnnotationGeometry {
  const geometry = annotation.geometry;
  if (annotation.type !== 'rectangle' || !('width' in geometry)) return geometry;

  const minWidth = Math.min(MIN_RESIZE_SIZE, item.width);
  const minHeight = Math.min(MIN_RESIZE_SIZE, item.height);
  let x = geometry.x;
  let y = geometry.y;
  let width = geometry.width;
  let height = geometry.height;

  if (handle.includes('w')) {
    x = clamp(point[0], 0, geometry.x + geometry.width - minWidth);
    width = geometry.x + geometry.width - x;
  } else if (handle.includes('e')) {
    width = clamp(point[0] - geometry.x, minWidth, item.width - geometry.x);
  }
  if (handle.includes('n')) {
    y = clamp(point[1], 0, geometry.y + geometry.height - minHeight);
    height = geometry.y + geometry.height - y;
  } else if (handle.includes('s')) {
    height = clamp(point[1] - geometry.y, minHeight, item.height - geometry.y);
  }

  return { x, y, width, height };
}

export type RoiRectangle = [number, number, number, number];

/** Move (handle = null) or resize the in-place ROI correction box in original pixels. */
export function editRoiRectangle(
  base: RoiRectangle,
  handle: RectangleResizeHandle | null,
  start: Point,
  point: Point,
  item: Pick<CaseRecord, 'width' | 'height'>,
): RoiRectangle {
  const asAnnotation = {
    shape_id: 'roi-edit', type: 'rectangle' as const, label: 'MICROANEURYSM' as const, source: 'HUMAN' as const, reviewer: '', created_at: '',
    geometry: { x: base[0], y: base[1], width: base[2] - base[0], height: base[3] - base[1] },
  };
  const geometry = handle
    ? resizeRectangleGeometry(asAnnotation, handle, point, item)
    : translateAnnotationGeometry(asAnnotation, [point[0] - start[0], point[1] - start[1]], item);
  if (!('width' in geometry)) return base;
  return [geometry.x, geometry.y, geometry.x + geometry.width, geometry.y + geometry.height];
}

export const ROI_HANDLES: RectangleResizeHandle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

export const HANDLE_CURSORS: Record<RectangleResizeHandle, string> = {
  nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize', n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize',
};

export function handlePoint(rect: RoiRectangle, handle: RectangleResizeHandle): Point {
  const [x1, y1, x2, y2] = rect;
  const x = handle.includes('w') ? x1 : handle.includes('e') ? x2 : (x1 + x2) / 2;
  const y = handle.includes('n') ? y1 : handle.includes('s') ? y2 : (y1 + y2) / 2;
  return [x, y];
}

export function sameRectangle(left: RoiRectangle, right: RoiRectangle) {
  return left.every((value, index) => Math.abs(value - right[index]) < 0.01);
}

export function annotationLocked(annotation: HumanAnnotation) {
  // Records written before lock persistence have no field and are protected by default.
  return annotation.locked !== false;
}

export function makeId() {
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function annotation(type: AnnotationType, label: LesionLabel, geometry: AnnotationGeometry): HumanAnnotation {
  return { shape_id: makeId(), type, label, geometry, locked: false, source: 'HUMAN', reviewer: '', created_at: '' };
}
