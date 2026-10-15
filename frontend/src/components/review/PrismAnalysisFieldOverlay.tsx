import { useEffect, useId, useRef, useState } from 'react';
import {
  Box,
  Flex,
  Image,
  SimpleGrid,
  Stack,
  Text,
} from '@chakra-ui/react';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';

export type PrismFovStatus = 'READY' | 'UNCERTAIN' | 'UNAVAILABLE';

const FIELD_TINT_OPACITY = 0.04;
const OUTSIDE_VEIL_OPACITY = 0.24;
const BOUNDARY_OPACITY = 0.82;
const BOUNDARY_UNDERLAY_OPACITY = 0.4;
const FEATHER_SIGMA_CSS_PX = 3.25;

interface PrismAnalysisFieldOverlayProps {
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  status: PrismFovStatus;
  fieldMaskImageUrl?: string;
  maskSha256?: string;
  maskVersion?: string;
  excludedFraction?: number;
  boundary?: ReadonlyArray<readonly [number, number]>;
}

function isUsableBoundary(
  boundary: PrismAnalysisFieldOverlayProps['boundary'],
  imageWidth: number,
  imageHeight: number,
): boundary is ReadonlyArray<readonly [number, number]> {
  return Boolean(boundary && boundary.length >= 3 && boundary.every((point) => (
    point.length === 2
    && Number.isFinite(point[0]) && Number.isFinite(point[1])
    && point[0] >= 0 && point[1] >= 0 && point[0] < imageWidth && point[1] < imageHeight
  )));
}

function isValidEvidence(props: PrismAnalysisFieldOverlayProps): boolean {
  return props.status === 'READY'
    && Number.isInteger(props.imageWidth) && props.imageWidth > 0
    && Number.isInteger(props.imageHeight) && props.imageHeight > 0
    && Boolean(props.fieldMaskImageUrl)
    && Boolean(props.maskVersion)
    && Boolean(props.maskSha256 && /^[a-f\d]{64}$/i.test(props.maskSha256))
    && Number.isFinite(props.excludedFraction)
    && (props.excludedFraction ?? -1) >= 0
    && (props.excludedFraction ?? 2) <= 1
    && isUsableBoundary(props.boundary, props.imageWidth, props.imageHeight);
}

function statusPresentation(status: PrismFovStatus, hasEvidence: boolean): {
  label: string;
  tone: StatusTone;
} {
  if (hasEvidence) return { label: 'Field prepared', tone: 'success' };
  if (status === 'UNCERTAIN') return { label: 'Boundary uncertain', tone: 'warning' };
  if (status === 'UNAVAILABLE') return { label: 'Not available', tone: 'neutral' };
  return { label: 'Boundary unavailable', tone: 'warning' };
}

export function PrismAnalysisFieldOverlay(props: PrismAnalysisFieldOverlayProps) {
  const {
    imageUrl,
    imageWidth,
    imageHeight,
    status,
    fieldMaskImageUrl,
    maskSha256,
    maskVersion,
    excludedFraction,
    boundary,
  } = props;
  const id = useId().replace(/:/g, '');
  const imageFrameRef = useRef<HTMLDivElement>(null);
  const [maskFeatherDeviation, setMaskFeatherDeviation] = useState(FEATHER_SIGMA_CSS_PX);
  const hasEvidence = isValidEvidence(props);
  const presentation = statusPresentation(status, hasEvidence);
  const fieldMaskId = `prismFieldMask-${id}`;
  const outsideMaskId = `prismOutsideMask-${id}`;
  const veilFilterId = `prismVeilMask-${id}`;
  const boundaryPath = hasEvidence && boundary
    ? `M ${boundary.map(([x, y]) => `${x} ${y}`).join(' L ')} Z`
    : '';
  const excludedArea = hasEvidence
    ? `${((excludedFraction ?? 0) * 100).toLocaleString('en', { maximumFractionDigits: 1 })}%`
    : 'Not available';

  useEffect(() => {
    const frame = imageFrameRef.current;
    if (!frame || !hasEvidence) return undefined;

    const updateFeather = () => {
      const rect = frame.getBoundingClientRect();
      const scale = Math.min(rect.width / imageWidth, rect.height / imageHeight);
      if (scale <= 0) return;
      const nextDeviation = Number((FEATHER_SIGMA_CSS_PX / scale).toFixed(3));
      setMaskFeatherDeviation((current) => (
        Math.abs(current - nextDeviation) < 0.01 ? current : nextDeviation
      ));
    };

    updateFeather();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(updateFeather);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [hasEvidence, imageHeight, imageWidth]);

  return (
    <Stack
      as="section"
      aria-label="PRISM Lesion Analysis Field"
      spacing={3}
      border="1px solid"
      borderColor="border.subtle"
      borderRadius="md"
      bg="surface.panel"
      p={{ base: 3, tablet: 4 }}
      minW={0}
    >
      <Flex
        justify="space-between"
        align={{ base: 'flex-start', tablet: 'center' }}
        direction={{ base: 'column', tablet: 'row' }}
        gap={2}
        minW={0}
      >
        <Stack spacing={0.5} minW={0}>
          <Text as="h2" fontSize="md" fontWeight="semibold">
            PRISM Lesion Analysis Field
          </Text>
          <Text fontSize="sm" color="text.secondary">
            Region included in lesion-analysis preprocessing
          </Text>
        </Stack>
        <StatusBadge tone={presentation.tone} flexShrink={0}>
          {presentation.label}
        </StatusBadge>
      </Flex>

      <Box
        ref={imageFrameRef}
        position="relative"
        width="100%"
        aspectRatio={`${imageWidth} / ${imageHeight}`}
        overflow="hidden"
        borderRadius="sm"
        bg="viewer.background"
      >
        <Image
          src={imageUrl}
          alt="Original image, unchanged"
          position="absolute"
          inset={0}
          width="100%"
          height="100%"
          objectFit="contain"
          draggable={false}
        />
        {hasEvidence && (
          <Box
            as="svg"
            position="absolute"
            inset={0}
            width="100%"
            height="100%"
            viewBox={`0 0 ${imageWidth} ${imageHeight}`}
            preserveAspectRatio="none"
            role="img"
            aria-label="PRISM analysis boundary; the included field is lightly highlighted and the excluded camera rim and outside field are dimmed."
            pointerEvents="none"
            data-mask-sha256={maskSha256}
          >
            <defs>
              <filter id={veilFilterId} colorInterpolationFilters="sRGB">
                <feComponentTransfer>
                  <feFuncR type="table" tableValues="1 0" />
                  <feFuncG type="table" tableValues="1 0" />
                  <feFuncB type="table" tableValues="1 0" />
                  <feFuncA type="identity" />
                </feComponentTransfer>
                <feGaussianBlur stdDeviation={maskFeatherDeviation} />
              </filter>
              <mask
                id={fieldMaskId}
                maskUnits="userSpaceOnUse"
                maskContentUnits="userSpaceOnUse"
                style={{ maskType: 'luminance' }}
                x={0}
                y={0}
                width={imageWidth}
                height={imageHeight}
              >
                <image
                  href={fieldMaskImageUrl}
                  x={0}
                  y={0}
                  width={imageWidth}
                  height={imageHeight}
                  preserveAspectRatio="none"
                />
              </mask>
              <mask
                id={outsideMaskId}
                maskUnits="userSpaceOnUse"
                maskContentUnits="userSpaceOnUse"
                style={{ maskType: 'luminance' }}
                x={0}
                y={0}
                width={imageWidth}
                height={imageHeight}
              >
                <image
                  href={fieldMaskImageUrl}
                  x={0}
                  y={0}
                  width={imageWidth}
                  height={imageHeight}
                  preserveAspectRatio="none"
                  filter={`url(#${veilFilterId})`}
                />
              </mask>
            </defs>
            <rect
              x={0}
              y={0}
              width={imageWidth}
              height={imageHeight}
              fill="#82B6B0"
              fillOpacity={FIELD_TINT_OPACITY}
              mask={`url(#${fieldMaskId})`}
            />
            <rect
              x={0}
              y={0}
              width={imageWidth}
              height={imageHeight}
              fill="#08100F"
              fillOpacity={OUTSIDE_VEIL_OPACITY}
              mask={`url(#${outsideMaskId})`}
            />
            <path
              d={boundaryPath}
              fill="none"
              stroke="#10211F"
              strokeOpacity={BOUNDARY_UNDERLAY_OPACITY}
              strokeWidth="2.4"
            />
            <path
              d={boundaryPath}
              fill="none"
              stroke="#E5F1EF"
              strokeOpacity={BOUNDARY_OPACITY}
              strokeWidth="1.3"
            />
          </Box>
        )}
      </Box>

      {hasEvidence ? (
        <>
          <SimpleGrid
            as="ul"
            aria-label="Analysis field legend"
            columns={{ base: 1, tablet: 2 }}
            spacing={{ base: 2, tablet: 3 }}
            listStyleType="none"
            m={0}
            p={0}
            fontSize="xs"
          >
            <Flex as="li" align="center" gap={2} minW={0}>
              <Box
                aria-hidden="true"
                width="12px"
                height="12px"
                flexShrink={0}
                bg="rgba(130, 182, 176, 0.22)"
                border="1px solid"
                borderColor="status.info"
              />
              <Text>Included in PRISM lesion analysis</Text>
            </Flex>
            <Flex as="li" align="center" gap={2} minW={0}>
              <Box
                aria-hidden="true"
                width="12px"
                height="12px"
                flexShrink={0}
                bg="#27302E"
                border="1px solid"
                borderColor="border.strong"
              />
              <Text>Excluded camera rim / outside analysis field</Text>
            </Flex>
            <Flex as="li" align="center" gap={2} minW={0}>
              <Box
                aria-hidden="true"
                width="18px"
                height="0"
                flexShrink={0}
                borderTop="2px solid"
                borderColor="status.info"
              />
              <Text>PRISM analysis boundary</Text>
            </Flex>
          </SimpleGrid>

        </>
      ) : null}

      <SimpleGrid
        as="dl"
        columns={{ base: 1, tablet: 3 }}
        spacing={{ base: 2, tablet: 4 }}
        borderTop="1px solid"
        borderColor="border.subtle"
        pt={3}
      >
        <Stack as="div" spacing={0.5}>
          <Text as="dt" fontSize="xs" color="text.secondary">Field version</Text>
          <Text as="dd" m={0} fontSize="sm" fontWeight="medium">{maskVersion || 'Not available'}</Text>
        </Stack>
        <Stack as="div" spacing={0.5}>
          <Text as="dt" fontSize="xs" color="text.secondary">Excluded area</Text>
          <Text as="dd" m={0} fontSize="sm" fontWeight="medium">{excludedArea}</Text>
        </Stack>
        <Stack as="div" spacing={0.5}>
          <Text as="dt" fontSize="xs" color="text.secondary">Original image</Text>
          <Text as="dd" m={0} fontSize="sm" fontWeight="medium">Unchanged</Text>
        </Stack>
      </SimpleGrid>

      {!hasEvidence && (
        <Stack
          spacing={1}
          borderLeft="3px solid"
          borderColor="status.warning"
          bg="status.warningSoft"
          px={3}
          py={2}
        >
          <Text fontSize="sm" fontWeight="medium">
            A validated PRISM analysis field is unavailable.
          </Text>
          <Text fontSize="xs" color="text.secondary">
            Automated PRISM-UWF processing is not prepared for this image.
          </Text>
        </Stack>
      )}

      <Stack spacing={0.5} bg="surface.subtle" borderRadius="sm" px={3} py={2}>
        <Text fontSize="xs" fontWeight="medium">
          Processing evidence only; not anatomical segmentation.
        </Text>
        <Text fontSize="xs" color="text.secondary">
          PRISM remains experimental and is not validated for UWF.
        </Text>
      </Stack>
    </Stack>
  );
}
