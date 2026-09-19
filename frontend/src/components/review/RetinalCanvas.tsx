import { Box, HStack, Image, Text } from '@chakra-ui/react';
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import type { CaseRecord, HumanAnnotation, Lesion, LesionLabel } from '@/lib/api';

export const LESION_COLORS: Record<LesionLabel, string> = {
  MICROANEURYSM: '#06B6D4',
  HEMORRHAGE: '#84CC16',
  HARD_EXUDATE: '#E879F9',
  SOFT_EXUDATE: '#6366F1',
};

export const LESION_SHORT_LABELS: Record<LesionLabel, string> = {
  MICROANEURYSM: 'MA',
  HEMORRHAGE: 'HE',
  HARD_EXUDATE: 'EX',
  SOFT_EXUDATE: 'SE',
};

interface RetinalCanvasProps {
  item: CaseRecord;
  showAi?: boolean;
  showHuman?: boolean;
  humanAnnotations?: HumanAnnotation[];
  selectedShapeId?: string | null;
  onSelectHuman?: (shapeId: string) => void;
  onPointerDown?: (event: ReactPointerEvent<SVGSVGElement>) => void;
  onPointerMove?: (event: ReactPointerEvent<SVGSVGElement>) => void;
  onPointerUp?: (event: ReactPointerEvent<SVGSVGElement>) => void;
  onDoubleClick?: (event: ReactPointerEvent<SVGSVGElement>) => void;
  children?: ReactNode;
}

function prettyLabel(label: string) {
  return label.replace(/_/g, ' ');
}

function labelPoint(lesion: Lesion) {
  return { x: lesion.rectangle[0], y: Math.max(14, lesion.rectangle[1] - 4) };
}

function annotationLabelPoint(annotation: HumanAnnotation) {
  const geometry = annotation.geometry;
  if ('points' in geometry) return { x: geometry.points[0][0], y: Math.max(14, geometry.points[0][1] - 4) };
  if ('cx' in geometry) return { x: geometry.cx - geometry.radius, y: Math.max(14, geometry.cy - geometry.radius - 4) };
  return { x: geometry.x, y: Math.max(14, geometry.y - 4) };
}

function AiShape({ lesion }: { lesion: Lesion }) {
  const [x1, y1, x2, y2] = lesion.rectangle;
  const color = LESION_COLORS[lesion.canonical_label as LesionLabel] ?? '#06B6D4';
  const label = prettyLabel(lesion.canonical_label);
  const textPoint = labelPoint(lesion);
  return (
    <g pointerEvents="auto">
      <title>{`AI suggestion: ${label} - score ${(lesion.score * 100).toFixed(1)}%`}</title>
      <rect
        x={x1}
        y={y1}
        width={x2 - x1}
        height={y2 - y1}
        fill={color}
        fillOpacity={0.12}
        stroke={color}
        strokeWidth={Math.max(2, (x2 - x1) / 120)}
        strokeDasharray="10 6"
        vectorEffect="non-scaling-stroke"
      />
      <text x={textPoint.x} y={textPoint.y} fill={color} fontSize={Math.max(10, Math.min(18, (x2 - x1) / 8))} fontWeight="700">
        {label}
      </text>
    </g>
  );
}

function HumanShape({
  annotation,
  selected,
  onSelect,
}: {
  annotation: HumanAnnotation;
  selected: boolean;
  onSelect?: (shapeId: string) => void;
}) {
  const color = LESION_COLORS[annotation.label];
  const common = {
    fill: color,
    fillOpacity: 0.3,
    stroke: selected ? '#111827' : color,
    strokeWidth: selected ? 4 : 3,
    vectorEffect: 'non-scaling-stroke' as const,
    onClick: (event: React.MouseEvent) => {
      event.stopPropagation();
      onSelect?.(annotation.shape_id);
    },
  };
  const geometry = annotation.geometry;
  return (
    <g>
      <title>{`HUMAN annotation: ${prettyLabel(annotation.label)}`}</title>
      {annotation.type === 'rectangle' && 'width' in geometry && <rect {...common} x={geometry.x} y={geometry.y} width={geometry.width} height={geometry.height} />}
      {annotation.type === 'polygon' && 'points' in geometry && <polygon {...common} points={geometry.points.map((point) => point.join(',')).join(' ')} />}
      {annotation.type === 'point' && 'x' in geometry && !('width' in geometry) && <circle {...common} cx={geometry.x} cy={geometry.y} r={Math.max(6, Math.min(18, Math.min(geometry.x, geometry.y) / 10))} />}
      {annotation.type === 'circle' && 'radius' in geometry && <circle {...common} cx={geometry.cx} cy={geometry.cy} r={geometry.radius} />}
      <text
        x={annotationLabelPoint(annotation).x}
        y={annotationLabelPoint(annotation).y}
        fill="#111827"
        fontSize="14"
        fontWeight="700"
        pointerEvents="none"
      >
        HUMAN - {LESION_SHORT_LABELS[annotation.label]}
      </text>
    </g>
  );
}

export function RetinalCanvas({
  item,
  showAi = true,
  showHuman = true,
  humanAnnotations = item.human_annotations,
  selectedShapeId,
  onSelectHuman,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onDoubleClick,
  children,
}: RetinalCanvasProps) {
  const aiLesions = item.lesion_review?.lesions ?? [];
  return (
    <Box>
      <Box
        position="relative"
        w="100%"
        aspectRatio={`${item.width} / ${item.height}`}
        bg="gray.950"
        borderRadius="md"
        overflow="hidden"
        sx={{ touchAction: 'none' }}
      >
        <Image
          src={item.image_url}
          alt={`${item.display_name} retinal image`}
          position="absolute"
          inset={0}
          w="100%"
          h="100%"
          objectFit="fill"
          userSelect="none"
          draggable={false}
        />
        <Box
          as="svg"
          position="absolute"
          inset={0}
          w="100%"
          h="100%"
          viewBox={`0 0 ${item.width} ${item.height}`}
          preserveAspectRatio="none"
          role="img"
          aria-label="Retinal image annotation canvas"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onDoubleClick={onDoubleClick}
        >
          {showAi && aiLesions.map((lesion, index) => <AiShape key={`ai-${index}`} lesion={lesion} />)}
          {showHuman && humanAnnotations.map((annotation) => (
            <HumanShape
              key={annotation.shape_id}
              annotation={annotation}
              selected={annotation.shape_id === selectedShapeId}
              onSelect={onSelectHuman}
            />
          ))}
          {children}
        </Box>
      </Box>
      <HStack mt={2} spacing={3} flexWrap="wrap" fontSize="xs" color="text.secondary">
        <Text fontWeight="semibold" color="text.primary">Legend</Text>
        <Text><Box as="span" display="inline-block" w="10px" h="10px" mr={1} bg="transparent" borderWidth="2px" borderStyle="dashed" borderColor="#06B6D4" />AI suggestion</Text>
        <Text><Box as="span" display="inline-block" w="10px" h="10px" mr={1} bg="#A73B244D" borderWidth="2px" borderColor="#A73B24" />Human</Text>
      </HStack>
    </Box>
  );
}
