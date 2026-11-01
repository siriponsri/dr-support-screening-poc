"""Review workflow routes: Original, display, analysis-area and mask-overlay image bytes.

Installed by `workflow.install_workflow`; code moved verbatim from workflow.py."""

from fastapi import HTTPException
from fastapi.responses import Response

from ..imaging import DerivativeError
from ..imaging.derivatives import (
    ANALYSIS_REPRESENTATION_VERSION,
    ANALYSIS_UWF_MASK_TRANSFORM,
    MASK_OVERLAY_REPRESENTATION_VERSION,
    render_mask_overlay,
)
from ..imaging.retinal_field import RetinalFieldNeedsReview


def install_images_routes(app, ctx):
    """Original, display, analysis-area and mask-overlay image bytes."""
    current_store = ctx.current_store
    admission_record = ctx.admission_record
    get_image = ctx.get_image

    @app.get('/v1/images/{image_id}')
    def image_bytes(image_id: str):
        image = get_image(image_id)
        return Response(image.data, media_type=image.media_type,
                        headers={'Cache-Control': 'private, max-age=3600'})

    @app.get('/v1/images/{image_id}/display')
    def display_image_bytes(image_id: str):
        image = app.state.images.get(image_id)
        if image is None:
            record = admission_record(image_id)
            status = (record or {}).get('integrity_status')
            if (record or {}).get('admission_reason_code') == 'DICOM_UNSUPPORTED_MODALITY':
                raise HTTPException(
                    409,
                    'This DICOM has an unsupported modality; it is not an ophthalmic retinal image for DR analysis.',
                )
            messages = {
                'DICOM_CODEC_REQUIRED': 'This DICOM image needs a supported pixel codec before it can be displayed.',
                'DICOM_MULTIFRAME_UNSUPPORTED': 'Multi-frame DICOM images require explicit frame selection before display.',
                'DECODE_FAILED': 'This DICOM image could not be decoded for display.',
                'UNSUPPORTED_FORMAT': 'This DICOM image is outside the supported display scope.',
            }
            if status in messages:
                raise HTTPException(409, messages[status])
            raise HTTPException(404, 'Image not admitted')
        try:
            derivative = app.state.derivatives.prepare_display(image)
        except DerivativeError as exc:
            record = admission_record(image_id)
            if (record or {}).get('admission_reason_code') == 'DICOM_UNSUPPORTED_MODALITY':
                raise HTTPException(
                    409,
                    'This DICOM has an unsupported modality; it is not an ophthalmic retinal image for DR analysis.',
                ) from None
            messages = {
                'DICOM_CODEC_REQUIRED': 'This DICOM image needs a supported pixel codec before it can be displayed.',
                'DICOM_MULTIFRAME_UNSUPPORTED': 'Multi-frame DICOM images require explicit frame selection before display.',
                'DECODE_FAILED': 'This DICOM image could not be decoded for display.',
                'UNSUPPORTED_FORMAT': 'This DICOM image is outside the supported display scope.',
            }
            raise HTTPException(
                409,
                messages.get(
                    getattr(exc, 'status', None),
                    'This image cannot be displayed in the browser. Review the source format or use a supported copy.',
                ),
            ) from None
        return Response(
            derivative.data,
            media_type=derivative.media_type,
            headers={
                'Cache-Control': 'private, max-age=3600',
                'ETag': f'"{derivative.lineage.derivative_sha256}"',
                'X-Source-SHA256': derivative.lineage.source_sha256,
                'X-Derivative-SHA256': derivative.lineage.derivative_sha256,
            },
        )

    @app.get('/v1/images/{image_id}/analysis-area')
    def analysis_area_bytes(image_id: str):
        """Inspect a confirmed UWF mask; never fall back to full source bytes."""
        image = get_image(image_id)
        record = admission_record(image_id) or {}
        preparation = current_store().get(image_id).get('analysis_preparation') or {}
        if record.get('retinal_modality') != 'UWF' or preparation.get('status') != 'READY':
            raise HTTPException(409, 'Analysis area is not available for this image.')
        try:
            derivative = app.state.derivatives.prepare_analysis(image, source_modality='UWF')
        except (DerivativeError, RetinalFieldNeedsReview):
            raise HTTPException(409, 'Analysis area could not be prepared.') from None
        expected = preparation.get('derivative') or {}
        audit = derivative.audit_record()
        if (expected.get('source_sha256') != audit['source_sha256']
                or expected.get('analysis_sha256') != audit['analysis_sha256']
                or expected.get('valid_retina_mask_sha256') != audit['valid_retina_mask_sha256']
                or expected.get('transform_id') != audit['transform_id']
                or (expected.get('representation_version') is not None
                    and expected.get('representation_version') != audit['representation_version'])
                or (expected.get('original_coordinate_space') is not None
                    and expected.get('original_coordinate_space') != audit['original_coordinate_space'])):
            raise HTTPException(409, 'Analysis area no longer matches its recorded source.')
        return Response(derivative.data, media_type=derivative.media_type,
                        headers={'Cache-Control': 'private, no-store',
                                 'X-Source-SHA256': image.sha256,
                                 'X-Analysis-SHA256': audit['analysis_sha256']})

    @app.get('/v1/images/{image_id}/mask-overlay')
    def mask_overlay_bytes(image_id: str):
        """Inspect the deterministic UWF mask over the immutable source image."""
        image = get_image(image_id)
        record = admission_record(image_id) or {}
        preparation = current_store().get(image_id).get('analysis_preparation') or {}
        status = preparation.get('status')
        if record.get('retinal_modality') != 'UWF' or status not in {'READY', 'NEEDS_REVIEW'}:
            raise HTTPException(409, 'Mask overlay is not available for this image.')
        expected_source = preparation.get('source_sha256') or (preparation.get('derivative') or {}).get('source_sha256')
        if expected_source != image.sha256:
            raise HTTPException(409, 'Mask overlay no longer matches its recorded source.')
        try:
            inspection = app.state.derivatives.inspect_analysis_mask(image, source_modality='UWF')
        except DerivativeError:
            raise HTTPException(409, 'Mask overlay could not be prepared.') from None
        if inspection.mask is None or inspection.mask_sha256 is None:
            raise HTTPException(409, 'No candidate mask is available for inspection.')
        if status == 'READY':
            expected = preparation.get('derivative') or {}
            try:
                regenerated = app.state.derivatives.prepare_analysis(image, source_modality='UWF')
            except (DerivativeError, RetinalFieldNeedsReview):
                raise HTTPException(409, 'Mask overlay could not be prepared.') from None
            audit = regenerated.audit_record()
            if (inspection.reason_code is not None
                    or expected.get('source_sha256') != image.sha256
                    or expected.get('analysis_sha256') != audit['analysis_sha256']
                    or expected.get('valid_retina_mask_sha256') != inspection.mask_sha256
                    or expected.get('transform_id') != ANALYSIS_UWF_MASK_TRANSFORM
                    or expected.get('representation_version') != ANALYSIS_REPRESENTATION_VERSION):
                raise HTTPException(409, 'Mask overlay no longer matches its recorded preparation.')
        else:
            if (preparation.get('reason_code') != inspection.reason_code
                    or preparation.get('candidate_mask_sha256') != inspection.mask_sha256
                    or preparation.get('candidate_mask_representation_version') != MASK_OVERLAY_REPRESENTATION_VERSION):
                raise HTTPException(409, 'Mask overlay no longer matches its recorded candidate.')
        return Response(
            render_mask_overlay(inspection.mask),
            media_type='image/png',
            headers={
                'Cache-Control': 'private, no-store',
                'X-Source-SHA256': image.sha256,
                'X-Mask-SHA256': inspection.mask_sha256,
                'X-Mask-Status': status,
                'X-Mask-Representation': MASK_OVERLAY_REPRESENTATION_VERSION,
            },
        )
