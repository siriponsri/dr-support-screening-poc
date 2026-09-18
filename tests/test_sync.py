import copy
import pytest
from dr_support.store import Store
from dr_support.sync import Sync
from dr_support.images import synthetic_image
from dr_support.providers.mock import infer_mock
from dr_support.contracts import InferenceRequest, LABELS
from dr_support.cvat import OnlineError


class RemoteFixture:
    def __init__(self):
        self.task = None
        self.payload = {'version': 0, 'tags': [], 'tracks': [], 'shapes': []}
        self.creates = self.uploads = self.pushes = 0

    def inspect(self):
        return {'id': 445923}, {label: i for i, label in enumerate(LABELS.values(), 1)}

    def find_task(self, name):
        return self.task

    def create_task(self, name):
        self.creates += 1
        self.task = {'id': 7, 'project_id': 445923, 'size': 0, 'name': name}
        return self.task

    def check_task(self, task_id):
        assert task_id == 7
        return self.task

    def upload(self, task_id, image):
        self.uploads += 1
        self.task['size'] = 1
        return {'rq_id': 'fixture-request'}

    def annotations(self, task_id):
        return copy.deepcopy(self.payload)

    def push(self, task_id, payload):
        self.pushes += 1
        self.payload = copy.deepcopy(payload)
        return self.payload

    def jobs(self, task_id):
        return {'results': [{'id': 9}]}


def setup(tmp_path):
    store = Store(tmp_path / 'review.sqlite')
    image = synthetic_image()
    case = store.get(image.image_id)
    case['lesion'] = infer_mock(InferenceRequest(image_id=image.image_id, model_id='mock-lesion'), image).model_dump(mode='json')
    store.put(case)
    remote = RemoteFixture()
    return store, image, remote, Sync(store, remote)


def test_idempotent_send_and_pull_preserve_corrections(tmp_path):
    store, image, remote, sync = setup(tmp_path)
    assert sync.send(image)['job_url'] == 'https://app.cvat.ai/tasks/7/jobs/9'
    sync.send(image)
    assert (remote.creates, remote.uploads, remote.pushes) == (1, 1, 1)
    remote.payload['shapes'][0]['points'] = [100, 100, 110, 110]
    remote.payload['shapes'][0]['source'] = 'manual'
    case = sync.pull(image)
    revision = case['revision']
    assert case['lesion_review_state'] == 'IMPORTED_REQUIRES_REVIEW'
    assert sync.pull(image)['revision'] == revision
    sync.send(image)
    assert remote.payload['shapes'][0]['points'] == [100, 100, 110, 110]
    reopened = Store(tmp_path / 'review.sqlite').get(image.image_id)
    assert reopened['annotation_hash'] == case['annotation_hash']


def test_ambiguous_push_never_retries_blindly(tmp_path):
    store, image, remote, sync = setup(tmp_path)
    def fail(*args):
        remote.pushes += 1
        raise OnlineError('Outcome unknown')
    remote.push = fail
    with pytest.raises(OnlineError):
        sync.send(image)
    with pytest.raises(OnlineError, match='manual reconciliation'):
        sync.send(image)
    assert remote.pushes == 1
