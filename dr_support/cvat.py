"""Dedicated CVAT Online transport. Secrets only from environment; no redirects."""
import os
import httpx
from dr_support.contracts import LABELS, LesionResult
from dr_support.presentation import review_selection


class OnlineError(RuntimeError):
    pass


class CVATOnline:
    def __init__(self, transport=None):
        self.base = os.environ.get('CVAT_URL', 'https://app.cvat.ai').rstrip('/')
        if self.base != 'https://app.cvat.ai':
            raise ValueError('This Bridge is restricted to https://app.cvat.ai')
        self.project_id = int(os.environ.get('CVAT_PROJECT_ID', '445923'))
        if self.project_id != 445923:
            raise ValueError('Only the owner-authorized project 445923 is admitted')
        self._transport = transport

    def request(self, method, path, **kwargs):
        if not path.startswith('/api/') or '..' in path or '://' in path:
            raise ValueError('Invalid API path')
        token = os.environ.get('CVAT_TOKEN')
        if not token:
            raise OnlineError('OWNER_ACTION_REQUIRED: inject CVAT_TOKEN into runtime environment')
        try:
            with httpx.Client(transport=self._transport, follow_redirects=False, timeout=30) as client:
                response = client.request(method, self.base + path,
                                          headers={'Authorization': 'Bearer ' + token}, **kwargs)
            if response.status_code >= 300:
                raise OnlineError(f'CVAT HTTP {response.status_code}; no success recorded')
            return response.json() if response.content else {}
        except (httpx.HTTPError, ValueError):
            raise OnlineError('CVAT transport/response failure; no success recorded') from None

    def inspect(self):
        self.request('GET', '/api/users/self')
        project = self.request('GET', f'/api/projects/{self.project_id}')
        labels = []
        page = 1
        while True:
            result = self.request('GET', '/api/labels', params={'project_id': self.project_id,
                                                              'page_size': 100, 'page': page})
            labels.extend(result['results'])
            if not result.get('next'):
                break
            page += 1
            if page > 100:
                raise OnlineError('Label pagination limit exceeded')
        mapping = {x['name']: x['id'] for x in labels}
        if not set(LABELS.values()).issubset(mapping):
            raise OnlineError('Project is missing required canonical lesion labels')
        return project, mapping

    def check_task(self, task_id):
        task = self.request('GET', f'/api/tasks/{int(task_id)}')
        if task.get('project_id') != self.project_id:
            raise OnlineError('Task is outside the authorized project')
        return task

    def find_task(self, name):
        result = self.request('GET', '/api/tasks', params={'project_id': self.project_id, 'search': name,
                                                          'page_size': 100})
        matches = [x for x in result['results'] if x['name'] == name and x['project_id'] == self.project_id]
        if len(matches) > 1 or result.get('next'):
            raise OnlineError('Ambiguous remote task mapping; manual reconciliation required')
        return matches[0] if matches else None

    def create_task(self, name):
        return self.request('POST', '/api/tasks', json={'name': name, 'project_id': self.project_id})

    def upload(self, task_id, image):
        if image.source_type not in ('PUBLIC', 'SYNTHETIC'):
            raise ValueError('Private data prohibited')
        self.check_task(task_id)
        extension, mime = ('.png', 'image/png') if image.data.startswith(b'\x89PNG') else ('.jpg', 'image/jpeg')
        return self.request('POST', f'/api/tasks/{int(task_id)}/data', data={'image_quality': '100'},
                            files={'client_files[0]': (image.image_id + extension, image.data, mime)})

    def annotations(self, task_id):
        self.check_task(task_id)
        return self.request('GET', f'/api/tasks/{int(task_id)}/annotations')

    def push(self, task_id, payload):
        self.check_task(task_id)
        # Never overwrite or delete existing manual annotations.
        return self.request('PATCH', f'/api/tasks/{int(task_id)}/annotations',
                            params={'action': 'create'}, json=payload)

    def jobs(self, task_id):
        self.check_task(task_id)
        return self.request('GET', '/api/jobs', params={'task_id': int(task_id), 'page_size': 100})


def rectangles(result: LesionResult, label_ids):
    selected, _ = review_selection(result)
    return {'version': 0, 'tags': [], 'tracks': [], 'shapes': [
        {'type': 'rectangle', 'frame': 0, 'label_id': label_ids[x.canonical_label],
         'points': list(x.rectangle), 'occluded': False, 'outside': False, 'rotation': 0,
         'z_order': 0, 'source': 'auto', 'attributes': []}
        for x in selected]}


def reviewed_shapes(payload, label_ids, width, height):
    """Preserve remote shapes; importing a shape never proves clinician confirmation."""
    import math
    names = {v: k for k, v in label_ids.items()}
    results = []
    for shape in payload.get('shapes', []):
        if shape.get('frame') != 0 or shape.get('label_id') not in names:
            raise ValueError('Unexpected frame or label in Bridge task')
        points = shape.get('points', [])
        shape_type = shape.get('type')
        if shape_type == 'mask':
            raise ValueError('Mask sync is not supported in Bridge v0.1.2; no mask data was imported')
        minimum = {'rectangle': 4, 'ellipse': 4, 'polygon': 6, 'polyline': 4, 'points': 2}.get(shape_type)
        if minimum is None or len(points) < minimum or (shape_type in ('rectangle', 'ellipse') and len(points) != 4):
            raise ValueError('Unsupported shape type or incomplete geometry; supported: rectangle, ellipse, polygon, polyline, points')
        if len(points) % 2 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in points):
            raise ValueError('Invalid geometry')
        if any(not 0 <= x <= width for x in points[::2]) or any(not 0 <= y <= height for y in points[1::2]):
            raise ValueError('Geometry outside original image')
        results.append({'remote_id': shape.get('id'), 'canonical_label': names[shape['label_id']],
                        'geometry': shape, 'state': 'IMPORTED_REQUIRES_REVIEW'})
    return results
