import { useEffect, useState } from 'react';
import { Alert, AlertIcon, Box, Image, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord } from '@/lib/api';

interface Field {
  schema_version: string; image_id: string; source_sha256: string; field_sha256: string;
  width: number | null; height: number | null; status: string; reason: string;
  method_version: string; model_input: string; core_fraction: number; uncertain_fraction: number;
  overlay_url: string | null; overlay_png_sha256: string | null;
}
const shaPattern = /^[a-f0-9]{64}$/;

/** Pure GET display; never prepares a model request or records physician review. */
export function ArtifactFieldPreview({ item }: { item: CaseRecord }) {
  const key = `${item.image_id}:${item.source_sha256}:${item.modality}`;
  const [state, setState] = useState<{ key: string; field?: Field; image?: string; error?: string; disabled?: boolean } | null>(null);
  useEffect(() => {
    if (item.modality !== 'UWF') return;
    const controller = new AbortController();
    let active = true;
    let asset: string | undefined;
    const route = `/v1/cases/${encodeURIComponent(item.image_id)}/artifact-roi/field`;
    const load = async () => {
      try {
        const response = await fetch(route, { signal: controller.signal, credentials: 'same-origin', cache: 'no-store' });
        if (response.status === 404) { if (active) setState({ key, disabled: true }); return; }
        if (!response.ok) throw new Error('Field unavailable');
        const field = await response.json() as Field;
        if (field.schema_version !== 'annotation-assist.image-only-field.v1' || field.image_id !== item.image_id
          || field.source_sha256 !== item.source_sha256 || !shaPattern.test(field.source_sha256)
          || !shaPattern.test(field.field_sha256) || field.model_input !== 'ORIGINAL_UNCHANGED'
          || !['READY_EMPIRICAL', 'RETAIN_ALL'].includes(field.status)
          || !Number.isFinite(field.core_fraction) || field.core_fraction < 0 || field.core_fraction > 1
          || !Number.isFinite(field.uncertain_fraction) || field.uncertain_fraction < 0 || field.uncertain_fraction > 1) throw new Error('Source binding changed');
        if (field.overlay_url) {
          const expected = `${route}/overlay?source_sha256=${field.source_sha256}&field_sha256=${field.field_sha256}`;
          if (field.overlay_url !== expected || !field.overlay_png_sha256 || !shaPattern.test(field.overlay_png_sha256)
            || field.width !== item.width || field.height !== item.height) throw new Error('Overlay binding changed');
          const image = await fetch(expected, { signal: controller.signal, credentials: 'same-origin', cache: 'no-store' });
          if (!image.ok || image.headers.get('X-Source-SHA256') !== field.source_sha256
            || image.headers.get('X-Field-SHA256') !== field.field_sha256) throw new Error('Overlay changed');
          const bytes = await image.arrayBuffer();
          if (bytes.byteLength > 32 * 1024 * 1024 || !crypto.subtle) throw new Error('Overlay verification unavailable');
          const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), (v) => v.toString(16).padStart(2, '0')).join('');
          if (hash !== field.overlay_png_sha256) throw new Error('Overlay bytes changed');
          if (!active || controller.signal.aborted) return;
          asset = URL.createObjectURL(new Blob([bytes], { type: 'image/png' }));
        }
        if (active) setState({ key, field, image: asset });
      } catch {
        if (active && !controller.signal.aborted) setState({ key, error: 'Image-only annotation field is unavailable. Original and inference remain unchanged; retain all suggestions.' });
      }
    };
    void load();
    return () => { active = false; controller.abort(); if (asset) URL.revokeObjectURL(asset); };
  }, [key, item.image_id, item.source_sha256, item.modality, item.width, item.height]);
  if (item.modality !== 'UWF' || (state?.key === key && state.disabled)) return null;
  const current = state?.key === key ? state : null;
  return <Stack spacing={2} data-testid="artifact-field-preview" borderWidth="1px" borderColor="border.subtle" p={3}>
    <Text fontWeight="semibold">Image-only annotation-assist field · before PRISM</Text>
    <Text fontSize="sm">This display helps locate empirical reflective-border candidates. PRISM still receives the unchanged Original image. It is not a model-input mask, anatomy segmentation, clinician confirmation or a normal/negative finding.</Text>
    {!current && <Text role="status">Preparing CPU image-only display; model readiness is not required…</Text>}
    {current?.error && <Alert status="warning"><AlertIcon /><Text>{current.error}</Text></Alert>}
    {current?.field && <>
      <Text fontSize="sm">{current.field.status === 'RETAIN_ALL' ? 'All suggestions retained; no exclusion is asserted.' : 'Empirical core candidate — uncalibrated and not proven technical padding.'}</Text>
      <Box as="details" fontSize="xs">
        <Box as="summary" cursor="pointer">Technical field details</Box>
        <Text>{current.field.method_version} · {current.field.reason}</Text>
      </Box>
      <Text fontSize="xs"><Box as="span" color="red.500">■</Box> Red: empirical core candidate {Math.round(current.field.core_fraction * 10000) / 100}% · <Box as="span" color="orange.500">■</Box> Amber: uncertain, retained {Math.round(current.field.uncertain_fraction * 10000) / 100}% · Other pixels: retained.</Text>
      {current.image && <Image src={current.image} alt="Source-bound annotation-assist display: empirical core red and uncertain retained area amber; actual PRISM input remains Original" maxH="420px" objectFit="contain" onError={() => setState({ key, error: 'Overlay could not be decoded. Original remains unchanged; retain all suggestions.' })} />}
      <Text fontSize="xs">Raw detections and restore remain available after inference. Zero visible boxes or a hidden candidate never creates a confirmed-negative or training-gold label.</Text>
    </>}
  </Stack>;
}
