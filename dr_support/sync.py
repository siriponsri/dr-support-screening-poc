"""CVAT transport orchestration; model internals never imported by the labeler."""
import hashlib
import json
from dr_support.contracts import LesionResult
from dr_support.cvat import rectangles, reviewed_shapes, OnlineError
from dr_support.presentation import lesion_review_view


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Sync:
    def __init__(self, store, remote):
        self.store, self.remote = store, remote

    def send(self, image):
        with self.store.lock:
            case = self.store.get(image.image_id)
            if not case['lesion']:
                raise ValueError('Run lesion inference before creating a CVAT task')
            result = LesionResult.model_validate(case['lesion'])
            if result.provenance.image_sha256 != image.sha256 or result.state != 'AI_SUGGESTION':
                raise ValueError('Prediction identity or modality mismatch')
            _, labels = self.remote.inspect()
            prediction_hash = digest({'raw_prediction': case['lesion'], 'review_view': lesion_review_view(case['lesion'])})
            mapping = case.get('cvat')
            if mapping and mapping['prediction_hash'] != prediction_hash:
                raise ValueError('Task is bound to an earlier prediction; preserve it and review manually')
            if not mapping:
                name = f'Bridge-{image.image_id}-{image.sha256[:12]}-{prediction_hash[:12]}'
                task = self.remote.find_task(name)
                if task is None:
                    task = self.remote.create_task(name)
                mapping = {'task_id': task['id'], 'prediction_hash': prediction_hash, 'sent': False,
                           'upload_started': bool(task.get('size')), 'push_started': False}
                case['cvat'] = mapping
                self.store.put(case)
            task_id = mapping['task_id']
            task = self.remote.check_task(task_id)
            if not task.get('size'):
                if mapping['upload_started']:
                    raise OnlineError('Upload pending or outcome unknown; inspect task before retrying')
                mapping['upload_started'] = True
                self.store.put(case)  # Durable intent before side effect; never duplicate uncertain writes.
                receipt = self.remote.upload(task_id, image)
                mapping['upload_receipt'] = receipt
                self.store.put(case)
                task = self.remote.check_task(task_id)
                if not task.get('size'):
                    raise OnlineError('Upload accepted; CVAT is processing. Retry sync when task is ready')
            if task['size'] != 1:
                raise ValueError('Bridge requires exactly one frame per task')
            annotations = self.remote.annotations(task_id)
            if not mapping['sent']:
                if annotations.get('shapes') or annotations.get('tags') or annotations.get('tracks'):
                    # Recovery or manual edits: preserve everything, do not append duplicate AI boxes.
                    mapping['sent'] = True
                    mapping['warning'] = 'Existing annotations preserved; auto-push skipped'
                elif mapping['push_started']:
                    raise OnlineError('Prior annotation push outcome unknown; manual reconciliation required')
                else:
                    mapping['push_started'] = True
                    self.store.put(case)
                    payload = rectangles(result, labels)
                    payload['version'] = annotations.get('version', 0)
                    self.remote.push(task_id, payload)
                    mapping['sent'] = True
            mapping['task_url'] = f'https://app.cvat.ai/tasks/{task_id}'
            jobs = self.remote.jobs(task_id)['results']
            if jobs:
                mapping['job_url'] = f'https://app.cvat.ai/tasks/{task_id}/jobs/{jobs[0]["id"]}'
            self.store.put(case)
            return mapping

    def pull(self, image):
        with self.store.lock:
            case = self.store.get(image.image_id)
            if not case.get('cvat'):
                raise ValueError('No CVAT task mapped')
            _, labels = self.remote.inspect()
            payload = self.remote.annotations(case['cvat']['task_id'])
            if payload.get('tracks') or payload.get('tags'):
                raise ValueError('Track/tag export requires manual review; no data silently discarded')
            shapes = reviewed_shapes(payload, labels, *image.size)
            fingerprint = digest(payload)
            if case.get('annotation_hash') != fingerprint:
                case['annotation_hash'] = fingerprint
                case['annotations'] = shapes
                case['annotation_raw'] = payload
                case['revision'] += 1
                case['lesion_review_state'] = 'IMPORTED_REQUIRES_REVIEW'
                case['events'].append({'action': 'CVAT_SYNC', 'annotation_hash': fingerprint})
                self.store.put(case)
            return case
