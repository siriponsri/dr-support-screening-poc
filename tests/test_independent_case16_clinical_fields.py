"""Generated fixture/copy-only store; no real image or provider calls."""
from copy import deepcopy
import pytest
from test_case16_authorization import metadata
from dr_support.services import case16_qualification as profile
from dr_support.services.prism_remote_transport import TransportError

@pytest.mark.parametrize('field,value',[
    ('lesion_review_state','REVIEWED'),
    ('annotation_completeness',{'MA':True,'HE':True,'EX':True,'SE':True}),
    ('annotations',{'human_confirmed':True,'lesions':[]}),
])
def test_copied_store_rejects_all_existing_clinical_review_fields(metadata,tmp_path,field,value):
    original=deepcopy(metadata.case)
    store=profile.QualificationMemoryStore(original,evidence=tmp_path/'testdata')
    changed=store.get(metadata.image.image_id)
    changed[field]=value
    with pytest.raises(TransportError,match='CLINICAL_MUTATION'):
        store.put(changed)
    assert store.get(metadata.image.image_id)==original
