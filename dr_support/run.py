"""Single-user localhost runtime; reverse-proxy authentication needed before remote hosting."""
import os
from pathlib import Path


def configure():
    root = Path(__file__).resolve().parents[1] / 'local-state/bridge'
    defaults = {'RETFOUND_SOURCE': root/'sources/RETFound', 'RETFOUND_WEIGHTS': root/'retfound-aptos.pth',
                'PRISM_SOURCE': root/'sources/PRISM-DR', 'PRISM_WEIGHTS': root/'prism'}
    for name, path in defaults.items():
        if path.exists():
            os.environ.setdefault(name, str(path))
    try:
        import torch
        torch.set_num_threads(int(os.environ.get('MODEL_CPU_THREADS','4')))
    except ImportError:
        pass


if __name__ == '__main__':
    configure()
    import uvicorn
    uvicorn.run('dr_support.api:app', host='127.0.0.1', port=8000, workers=1)
