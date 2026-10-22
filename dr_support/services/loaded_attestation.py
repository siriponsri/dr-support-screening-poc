"""Technical loaded-model identity only; no clinical admission semantics."""
from .prism_remote_transport import TransportError

REASONS = frozenset({'LOADED_ATTESTATION_BODY_TYPE', 'LOADED_ATTESTATION_KEYS', 'LOADED_ATTESTATION_STATE', 'LOADED_ATTESTATION_PINS_TYPE', 'LOADED_ATTESTATION_PINS_MISMATCH', 'LOADED_ATTESTATION_EPOCH'})


def require_loaded_identity(value, *, expected_pins, expected_epoch):
    evidence = {
        'body_is_object': isinstance(value, dict),
        'keys_match': isinstance(value, dict) and set(value) == {'state', 'pins', 'epoch'},
        'state_matches': isinstance(value, dict) and value.get('state') == 'LOADED',
        'pins_is_object': isinstance(value, dict) and isinstance(value.get('pins'), dict),
        'pins_match': isinstance(value, dict) and value.get('pins') == expected_pins,
        'epoch_matches': isinstance(value, dict) and value.get('epoch') == expected_epoch,
    }
    ordered = [('body_is_object','LOADED_ATTESTATION_BODY_TYPE'), ('keys_match','LOADED_ATTESTATION_KEYS'), ('state_matches','LOADED_ATTESTATION_STATE'), ('pins_is_object','LOADED_ATTESTATION_PINS_TYPE'), ('pins_match','LOADED_ATTESTATION_PINS_MISMATCH'), ('epoch_matches','LOADED_ATTESTATION_EPOCH')]
    for key, reason in ordered:
        if not evidence[key]:
            error = TransportError(reason, 503)
            error.attestation_evidence = evidence
            raise error
    return evidence
