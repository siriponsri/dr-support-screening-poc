"""Official RETFound MAE five-class APTOS adapter. No encoder-only grading."""
import importlib.util
import io
import os

from dr_support.contracts import GlobalResult, Provenance
from dr_support.runtime import resolve_device, runtime_snapshot
from .assets import verify_source, verify_weight

REVISION = 'ae9a9ecf37857cf47b8aa9f87cd6f710d75db287'
WEIGHT_SHA256 = 'a96b9dbcb78eff373912fb0a48d316dc35ffb0715bb2a1b9128b096d780edbbf'
PREPROCESSING = 'RGB; resize short edge 256 bicubic; center crop 224; ImageNet mean/std; global pool'


class RETFound:
    task = 'global'
    model_id = 'retfound-aptos5'

    def __init__(self, *, allow_cpu_fallback: bool | None = None):
        """Construct the RETFound adapter.

        ``allow_cpu_fallback`` controls behaviour when the configured device
        starts with ``cuda`` but no CUDA runtime is available. The production
        model_api factory passes ``False`` so misconfigured GPU hosts fail
        loudly; local development and contract tests pass ``True`` so the
        adapter can be instantiated on a CPU-only host.
        """
        self.model = None
        self.device = None
        self._allow_cpu_fallback = allow_cpu_fallback

    def _resolve_device(self):
        return resolve_device(allow_cpu_fallback=self._allow_cpu_fallback)

    def metadata(self):
        configured = all(os.environ.get(k) for k in ('RETFOUND_SOURCE', 'RETFOUND_WEIGHTS'))
        snap = runtime_snapshot()
        warnings = ['CC-BY-NC-4.0; research/non-commercial only', 'Uncalibrated Bridge model; not R1 champion']
        requested = snap.requested_device
        effective = snap.effective_device
        # Surface device honesty: if the request could not be honoured we
        # warn loudly rather than pretending the model will run on GPU.
        if requested.startswith('cuda') and effective != requested:
            warnings.append(
                f"INFERENCE_DEVICE={requested} requested but unavailable; "
                f'effective_device={effective}.'
            )
        return {
            'model_id': self.model_id,
            'task': self.task,
            'revision': REVISION,
            'status': 'LOADED' if self.model is not None else (
                'CONFIGURED_NOT_VERIFIED' if configured else 'ASSET_REQUIRED'
            ),
            'modalities': ['CFP'],
            'class_order': [0, 1, 2, 3, 4],
            'requested_device': requested,
            'effective_device': self.device or effective,
            'cuda_available': snap.cuda_available,
            'warnings': warnings,
            'preprocessing': PREPROCESSING,
        }

    def load(self):
        import torch
        from argparse import Namespace
        device = self._resolve_device()
        source = verify_source(os.environ['RETFOUND_SOURCE'], REVISION)
        weight = verify_weight(os.environ['RETFOUND_WEIGHTS'], WEIGHT_SHA256)
        spec = importlib.util.spec_from_file_location('drsupport_retfound_vit', source / 'models_vit.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        model = module.RETFound_mae(num_classes=5, global_pool=True)
        # Always load the checkpoint into CPU memory first (the file lives on
        # the GPU host's RAM/SSD). We then move the parameters to the resolved
        # device so the inference runs there. map_location='cpu' is the safe
        # choice even when the target device is CUDA.
        with torch.serialization.safe_globals([Namespace]):
            checkpoint = torch.load(weight, map_location='cpu', weights_only=True, mmap=True)
        state = checkpoint.get('model', checkpoint)
        if 'head.weight' not in state or tuple(state['head.weight'].shape) != (5, 1024):
            raise RuntimeError('Fine-tuned five-class DR head required; pretrained encoder cannot grade')
        model.load_state_dict(state, strict=True)
        model = model.to(device)
        # ``inference_mode`` is the upstream-recommended tight autograd guard
        # for evaluation; we enable it both at load time (so it covers the
        # forward pass) and around each ``infer`` call so direct callers
        # cannot accidentally re-enable autograd.
        model.eval()
        for p in model.parameters():
            p.requires_grad_(False)
        self.model = model
        self.device = device

    def infer(self, request, image):
        import torch
        from PIL import Image
        from torchvision import transforms
        provenance = Provenance(image_sha256=image.sha256, source_type=image.source_type,
                                source_revision=REVISION, preprocessing=PREPROCESSING,
                                checkpoint_sha256={'aptos5': WEIGHT_SHA256})
        common = dict(model_id=self.model_id, model_version=REVISION, modality=request.modality,
                      provenance=provenance, warnings=self.metadata()['warnings'])
        if request.modality != 'CFP':
            return GlobalResult(**common, state='UNSUPPORTED')
        if self.model is None:
            self.load()
        device = self.device or self._resolve_device()
        transform = transforms.Compose([
            transforms.Resize(256, interpolation=transforms.InterpolationMode.BICUBIC),
            transforms.CenterCrop(224), transforms.ToTensor(),
            transforms.Normalize([.485, .456, .406], [.229, .224, .225])])
        with Image.open(io.BytesIO(image.data)) as pil:
            tensor = transform(pil.convert('RGB')).unsqueeze(0)
        # Move the input tensor to the resolved device so the forward pass
        # executes there. Combined with the model already on `device`, this
        # keeps every tensor on the same runtime.
        tensor = tensor.to(device)
        with torch.inference_mode():
            # Pinned upstream global-pool features have a singleton token axis.
            features = self.model.forward_features(tensor)
            logits = self.model.head(features).reshape(1, 5)
            probabilities = logits.softmax(-1)[0].tolist()
        grade = max(range(5), key=probabilities.__getitem__)
        return GlobalResult(**common, state='AI_SUGGESTION', grade=grade,
                            probabilities=probabilities, confidence=probabilities[grade])
