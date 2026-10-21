import { useEffect, useRef, useState } from 'react';
import { Alert, AlertIcon, Box, Button, Checkbox, Code, HStack, Image, SimpleGrid, Stack, Text } from '@chakra-ui/react';
import { apiJson, type CaseRecord, type ModelDescriptor } from '@/lib/api';
import { loadPreviewAsset, previewContextKey, validatePrismPreview, type PrismInputPreview as PreviewPlan } from '@/lib/prismInputPreview';
import { localTiming, type TimingSpan } from '@/lib/localTiming';

interface Props { item: CaseRecord; model: ModelDescriptor; onInferenceComplete?: () => void | Promise<void> }
interface Assets { key: string; original: string; input: string; overlay: string | null }

/** Read-only preparation view. It never calls an inference or clinical-action API. */
export function PrismInputPreview({ item, model, onInferenceComplete }: Props) {
  const [open, setOpen] = useState(false);
  const [assets, setAssets] = useState<Assets | null>(null);
  const [error, setError] = useState<{ key: string; message: string } | null>(null);
  const [overlay, setOverlay] = useState(true);
  const [opacity, setOpacity] = useState(60);
  const [zoom, setZoom] = useState(100);
  const [, tick] = useState(0);
  const context = previewContextKey(item, model);
  const [prepared, setPrepared] = useState<{ context: string; value: unknown } | null>(null);
  const [actionError, setActionError] = useState<{ context: string; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [acceptedKey, setAcceptedKey] = useState<string | null>(null);
  const [submittedKey, setSubmittedKey] = useState<string | null>(null);
  const action = useRef<{ controller: AbortController; context: string } | null>(null);
  const assetTiming = useRef<{ key: string; span: TimingSpan; loaded: Set<string> } | null>(null);
  const value = prepared?.context === context ? prepared.value : item.prism_input_preview;
  const key = context + JSON.stringify(value);
  let plan: PreviewPlan | undefined;
  let unavailable = '';
  try { plan = validatePrismPreview(value, item, model); }
  catch (err) { unavailable = err instanceof Error ? err.message : 'Preview unavailable.'; }

  useEffect(() => {
    setBusy(false);
    return () => { action.current?.controller.abort(); action.current = null; };
  }, [context]);

  const prepare = async () => {
    if (action.current) return;
    const current = { controller: new AbortController(), context };
    action.current = current;
    setBusy(true);
    setPrepared(null);
    setAcceptedKey(null);
    setActionError(null);
    try {
      const result = await apiJson<unknown>(`/v1/cases/${encodeURIComponent(item.image_id)}/prism-input-preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        signal: current.controller.signal, body: JSON.stringify({ revision: item.revision, model_id: model.model_id }),
      });
      if (action.current === current && !current.controller.signal.aborted) setPrepared({ context, value: result });
    } catch (err) {
      if (action.current === current && !current.controller.signal.aborted) setActionError({ context, message: err instanceof Error ? err.message : 'Preparation failed.' });
    } finally {
      if (action.current === current) { action.current = null; setBusy(false); }
    }
  };

  useEffect(() => {
    if (!open || unavailable || !plan) return;
    const controller = new AbortController();
    const urls: string[] = [];
    let active = true;
    const timing = localTiming.start('preview_assets', item.image_id);
    assetTiming.current = { key, span: timing, loaded: new Set() };
    const verifiedPlan = plan;
    const load = async (asset: Parameters<typeof loadPreviewAsset>[0], width: number, height: number) => {
      const url = await loadPreviewAsset(asset, width, height, controller.signal);
      urls.push(url);
      if (!active) URL.revokeObjectURL(url);
      return url;
    };
    setError(null);
    setAssets(null);
    void Promise.all([
      load(verifiedPlan.original_preview, item.width, item.height),
      load(verifiedPlan.input_preview, verifiedPlan.transform.input_width, verifiedPlan.transform.input_height),
      verifiedPlan.overlay ? load(verifiedPlan.overlay, item.width, item.height) : Promise.resolve(null),
    ]).then(([original, input, mask]) => {
      if (active) setAssets({ key, original: original!, input: input!, overlay: mask });
    }).catch((err: unknown) => {
      timing.end(controller.signal.aborted ? 'ABORTED' : 'FAILED');
      if (active) {
        controller.abort();
        urls.forEach((url) => URL.revokeObjectURL(url));
        setAssets(null);
        setError({ key, message: err instanceof Error ? err.message : 'Preview failed.' });
      }
    });
    let expires: ReturnType<typeof setTimeout>;
    const checkExpiry = () => {
      const remaining = Date.parse(verifiedPlan.expires_at) - Date.now();
      if (remaining <= 0) tick((value) => value + 1);
      else expires = setTimeout(checkExpiry, Math.min(60_000, remaining));
    };
    checkExpiry();
    return () => {
      timing.end('ABORTED');
      active = false;
      controller.abort();
      clearTimeout(expires);
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
    // key includes the entire source/model/preparation/plan identity. Never show old assets during effect cleanup.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, open, unavailable]);

  const shown = open && !unavailable && assets?.key === key && error?.key !== key ? assets : null;
  const failImage = () => { assetTiming.current?.span.end('FAILED'); setAssets(null); setError({ key, message: 'Preview image could not be decoded. Reload the case.' }); };
  const imageReady = (kind: string) => {
    const current = assetTiming.current;
    if (!current || current.key !== key || current.loaded.size === 2) return;
    current.loaded.add(kind);
    if (current.loaded.size === 2) { current.span.end('COMPLETED'); localTiming.event('preview_ready', item.image_id); }
  };
  const submit = async () => {
    if (action.current || !shown || !plan || acceptedKey !== key || submittedKey === key || plan.submission_binding_enforced !== true) return;
    // Revalidate expiry/context at the actual click, before the server's atomic check.
    let verified: PreviewPlan;
    try { verified = validatePrismPreview(value, item, model); }
    catch { setError({ key, message: 'Preview expired or changed; prepare it again.' }); return; }
    const current = { controller: new AbortController(), context };
    action.current = current;
    setBusy(true);
    setSubmittedKey(key); // Never automatically replay a timed-out/failed invocation.
    setAcceptedKey(null);
    setActionError(null);
    try {
      await apiJson(`/v1/cases/${encodeURIComponent(item.image_id)}/prism-input-preview/${encodeURIComponent(verified.plan_id)}/infer`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: current.controller.signal,
        body: JSON.stringify({ revision: item.revision, source_sha256: verified.source_sha256,
          wire_sha256: verified.wire_sha256, plan_sha256: verified.plan_sha256,
          mask_sha256: verified.mask.sha256, transform_sha256: verified.transform.sha256, model_version: verified.model_version }),
      }, { model_id: model.model_id, model_version: verified.model_version });
      if (action.current === current && !current.controller.signal.aborted) await onInferenceComplete?.();
    } catch (err) {
      if (action.current === current && !current.controller.signal.aborted) setActionError({ context, message: err instanceof Error ? err.message : 'Submission failed; do not retry this receipt.' });
    } finally {
      if (action.current === current) { action.current = null; setBusy(false); }
    }
  };
  return (
    <Stack spacing={3} borderTopWidth="1px" borderColor="border.subtle" pt={4} mt={4} aria-label="Pre-submission PRISM preview">
      <Button alignSelf="flex-start" size="sm" variant="outline" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        {open ? 'Hide PRISM input preview' : 'Preview PRISM input'}
      </Button>
      <Text fontSize="xs" color="text.secondary">PRISM requires a server-verified, one-use input receipt. Providers without frozen-plan support remain unavailable. Global grading and manual review remain separate.</Text>
      {open && <>
        <Button alignSelf="flex-start" size="sm" variant="outline" isLoading={busy} onClick={() => void prepare()}>Prepare / refresh API input</Button>
        {actionError?.context === context && <Alert status="error"><AlertIcon /><Text>{actionError.message} Prepare a new receipt before another attempt.</Text></Alert>}
        <Text fontSize="sm">Optical FOV is the camera field; an artifact mask excludes selected pixels; native ROI is PRISM’s internal crop. None is a lesion box or a clinical grade.</Text>
        {(unavailable || error?.key === key) ? <Alert status="warning"><AlertIcon /><Stack spacing={1}>
          <Text fontWeight="semibold">PRISM input preview unavailable</Text>
          <Text fontSize="sm">{unavailable || error?.message}</Text>
          <Text fontSize="sm">Original remains the review source. A candidate mask or a previous run cannot establish the next input. PRISM cannot be submitted without a verified receipt.</Text>
        </Stack></Alert> : plan && <>
          <Alert status="info"><AlertIcon /><Stack spacing={1}>
            <Text fontWeight="semibold">Planned API input — internal model crop not previewed</Text>
            <Text fontSize="sm">This preview covers only the planned API submission. PRISM may subsequently crop, resize or tile internally; those final model inputs are not shown. Browser verification checks the displayed PNG bytes; wire provenance remains a server attestation.</Text>
            <Text fontSize="sm">Native ROI: NOT_RUN. {plan.mask_application === 'CONDITIONAL_ON_NATIVE_ROI_SUCCESS'
              ? 'The optical FOV is a conditional candidate, not an applied mask. It can be used only if native ROI succeeds. If native ROI fails, the baseline discards the candidate and uses full Original.'
              : 'No external mask is planned. Native ROI may still crop internally; if native ROI fails, the baseline uses full Original.'}</Text>
            <Text fontSize="sm">External FOV: {plan.external_fov_status}{plan.external_fov_reason_code ? ` · ${plan.external_fov_reason_code}` : ''}. This is technical preparation status, not a clinical finding.</Text>
            {plan.input_kind === 'ORIGINAL_FALLBACK' && <Text fontSize="sm">Original wire fallback: {plan.fallback_reason}. This does not mean native ROI cropping is disabled.</Text>}
          </Stack></Alert>
          {!shown && <Text role="status">Verifying immutable preview image bytes…</Text>}
          {shown && <>
            <HStack flexWrap="wrap" spacing={4}>
              <Checkbox isChecked={Boolean(shown.overlay) && overlay} isDisabled={!shown.overlay} onChange={(event) => setOverlay(event.target.checked)}>Show conditional FOV overlay</Checkbox>
              {!shown.overlay && <Text fontSize="xs">No conditional overlay available.</Text>}
              <Box as="label" fontSize="sm">Overlay opacity {opacity}% <input aria-label="Processing overlay opacity" type="range" min="0" max="100" value={opacity} disabled={!shown.overlay || !overlay} onChange={(event) => setOpacity(Number(event.target.value))} /></Box>
              <Box as="label" fontSize="sm">Preview zoom {zoom}% <input aria-label="PRISM preview zoom" type="range" min="100" max="300" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} /></Box>
            </HStack>
            <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={3} minW={0}>
              {(['original', 'input'] as const).map((kind) => <Box key={kind} minW={0}>
                <Text fontSize="sm" fontWeight="semibold" mb={2}>{kind === 'original' ? 'Original' : 'Planned API submission'}</Text>
                <Box overflow="auto" maxH="420px" tabIndex={0} aria-label={`${kind} preview scroll area`} bg="gray.900">
                  <Box position="relative" width={`${zoom}%`}>
                    <Image src={shown[kind]} alt={kind === 'original' ? 'Verified original preview' : 'Verified planned input preview'} width="100%" maxW="none" onLoad={() => imageReady(kind)} onError={failImage} />
                    {kind === 'original' && overlay && shown.overlay && <Image src={shown.overlay} alt="Processing overlay in original-image coordinates" position="absolute" inset={0} width="100%" height="100%" opacity={opacity / 100} pointerEvents="none" onError={failImage} />}
                  </Box>
                </Box>
              </Box>)}
            </SimpleGrid>
            <Text fontSize="xs" fontWeight="semibold">{plan.mask.kind === 'NONE' ? 'Coverage at this stage — no external mask' : 'Conditional candidate coverage — not an applied mask'}</Text>
            <HStack flexWrap="wrap" spacing={3} aria-label="Processing coverage legend">
              <Text fontSize="xs"><Box as="span" color="green.600">■</Box> Retained {Math.round(plan.retained_fraction * 100)}%</Text>
              <Text fontSize="xs"><Box as="span" color="red.600">■</Box> Excluded {Math.round(plan.excluded_fraction * 100)}%</Text>
              <Text fontSize="xs"><Box as="span" color="orange.600">■</Box> Uncertain {Math.round(plan.uncertain_fraction * 100)}%</Text>
            </HStack>
            <Text fontSize="xs">Mask: {plan.mask.kind} · {plan.mask.version}. Overlay is processing evidence in original coordinates; retained does not mean clinically normal. Uncertain pixels are not silently excluded.</Text>
            <Box as="details" fontSize="xs" overflowWrap="anywhere"><Box as="summary" cursor="pointer">Preview provenance</Box>
              <Text>Plan <Code>{plan.plan_id}</Code> · revision {plan.case_revision}</Text>
              <Text>Source SHA256: {plan.source_sha256}</Text><Text>Mask SHA256: {plan.mask.sha256 ?? 'none'}</Text>
              <Text>Wire SHA256: {plan.wire_sha256} · {plan.wire_media_type} · {plan.wire_byte_count} bytes</Text>
              <Text>Plan SHA256: {plan.plan_sha256}</Text><Text>Transform {plan.transform.version}: {plan.transform.sha256}</Text>
              <Text>Input RGB SHA256 (server attestation): {plan.input_preview.rgb_sha256}</Text>
              <Text>Model {plan.model_id} / {plan.model_version}; expires {plan.expires_at}</Text>
            </Box>
            {plan.submission_binding_enforced === true ? <>
              <Checkbox isChecked={acceptedKey === key} isDisabled={busy || submittedKey === key} onChange={(event) => setAcceptedKey(event.target.checked ? key : null)}>I inspected the planned API input; the internal model crop is not previewed.</Checkbox>
              <Button alignSelf="flex-start" isLoading={busy} isDisabled={acceptedKey !== key || submittedKey === key} onClick={() => void submit()}>Submit prepared input to PRISM</Button>
              {submittedKey === key && <Text fontSize="xs">This receipt has been submitted. Prepare a new preview for another attempt.</Text>}
            </> : <Text fontSize="sm">Submission unavailable: this display plan does not attest backend execution binding.</Text>}
          </>}
        </>}
      </>}
    </Stack>
  );
}
