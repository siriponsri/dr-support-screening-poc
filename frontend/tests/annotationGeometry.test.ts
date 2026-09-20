import { pointFromEvent, resizeRectangleGeometry, translateAnnotationGeometry } from '@/pages/AnnotationEditorPage';
import type { CaseRecord, HumanAnnotation } from '@/lib/api';

const bounds = { width: 800, height: 600 } as Pick<CaseRecord, 'width' | 'height'>;

function human(type: HumanAnnotation['type'], geometry: HumanAnnotation['geometry']): HumanAnnotation {
  return {
    shape_id: 'human-1',
    type,
    label: 'MICROANEURYSM',
    geometry,
    locked: false,
    source: 'HUMAN',
    reviewer: 'test',
    created_at: '',
  };
}

describe('human annotation movement', () => {
  it('translates rectangles in original pixels and clamps them to the image', () => {
    const annotation = human('rectangle', { x: 100, y: 120, width: 200, height: 160 });

    expect(translateAnnotationGeometry(annotation, [50, -20], bounds)).toEqual({
      x: 150, y: 100, width: 200, height: 160,
    });
    expect(translateAnnotationGeometry(annotation, [-500, 600], bounds)).toEqual({
      x: 0, y: 440, width: 200, height: 160,
    });
  });

  it('keeps polygon, point, and circle geometry aligned and in bounds', () => {
    expect(translateAnnotationGeometry(human('polygon', { points: [[10, 20], [50, 20], [40, 60]] }), [-20, 580], bounds)).toEqual({
      points: [[0, 560], [40, 560], [30, 600]],
    });
    expect(translateAnnotationGeometry(human('point', { x: 10, y: 20 }), [-40, 700], bounds)).toEqual({ x: 0, y: 600 });
    expect(translateAnnotationGeometry(human('circle', { cx: 100, cy: 100, radius: 20 }), [900, -200], bounds)).toEqual({ cx: 780, cy: 20, radius: 20 });
  });
});

describe('human rectangle resize', () => {
  const rectangle = human('rectangle', { x: 100, y: 120, width: 200, height: 160 });

  it('transforms each handle in original-image pixels and clamps to bounds/minimum size', () => {
    expect(resizeRectangleGeometry(rectangle, 'se', [350, 320], bounds)).toEqual({ x: 100, y: 120, width: 250, height: 200 });
    expect(resizeRectangleGeometry(rectangle, 'nw', [-100, -100], bounds)).toEqual({ x: 0, y: 0, width: 300, height: 280 });
    expect(resizeRectangleGeometry(rectangle, 'e', [102, 200], bounds)).toEqual({ x: 100, y: 120, width: 4, height: 160 });
    expect(resizeRectangleGeometry(rectangle, 's', [200, 999], bounds)).toEqual({ x: 100, y: 120, width: 200, height: 480 });
  });

  it('maps pointer coordinates correctly when the transformed stage is zoomed and panned', () => {
    const event = { currentTarget: { getBoundingClientRect: () => ({ left: 80, top: 40, width: 1600, height: 1200 }) }, clientX: 480, clientY: 640 } as unknown as Parameters<typeof pointFromEvent>[0];
    const point = pointFromEvent(event, bounds);
    expect(point).toEqual([200, 300]);
    expect(resizeRectangleGeometry(rectangle, 'se', point, bounds)).toEqual({ x: 100, y: 120, width: 100, height: 180 });
  });
});
