"""Check pinned packages and native libraries in the Group 19 environment."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[1]

PROBES = {
    "NumPy, pandas, SciPy, scikit-learn and h5py": """
        import numpy as np
        import pandas as pd
        import scipy.linalg
        import sklearn
        from sklearn.tree import DecisionTreeClassifier
        import h5py
        assert np.linalg.det(np.eye(2)) == 1.0
        assert pd.Series([1, 2, 3]).sum() == 6
        assert scipy.linalg.det(np.eye(2)) == 1.0
        model = DecisionTreeClassifier(random_state=0).fit([[0], [1]], [0, 1])
        assert model.predict([[1]]).tolist() == [1]
        print('Numerical libraries: native operations passed')
    """,
    "Numba and llvmlite JIT": """
        import numba
        import llvmlite
        def square_plus_one(value):
            return value * value + 1
        compiled = numba.njit(square_plus_one)
        assert compiled(3) == 10
        print('Numba', numba.__version__, 'llvmlite', llvmlite.__version__)
    """,
    "PyTorch, TorchVision, TorchAudio and NumPy bridge": """
        import numpy as np
        import torch
        import torchvision
        import torchaudio
        array = np.arange(3, dtype=np.float32)
        np.testing.assert_array_equal(torch.from_numpy(array).numpy(), array)
        assert torch.tensor([1.0, 2.0]).sum().item() == 3.0
        boxes = torch.tensor([[0., 0., 2., 2.], [0., 0., 2., 2.]])
        scores = torch.tensor([0.9, 0.8])
        assert torchvision.ops.nms(boxes, scores, 0.5).tolist() == [0]
        audio = torchaudio.functional.resample(torch.zeros(1, 32), 16000, 8000)
        assert tuple(audio.shape) == (1, 16)
        print('torch', torch.__version__, 'torchvision', torchvision.__version__,
              'torchaudio', torchaudio.__version__)
        print('CUDA runtime:', torch.version.cuda,
              'device available:', torch.cuda.is_available())
    """,
    "TensorFlow and Keras": """
        import tensorflow as tf
        import keras
        assert float(tf.reduce_sum(tf.constant([1.0, 2.0])).numpy()) == 3.0
        output = keras.layers.Dense(1)(tf.ones((1, 2)))
        assert tuple(output.shape) == (1, 1)
        print('TensorFlow', tf.__version__, 'Keras', keras.__version__)
    """,
    "Remaining pinned package imports": """
        import importlib
        modules = (
            'absl', 'astunparse', 'certifi', 'charset_normalizer', 'filelock',
            'flatbuffers', 'fsspec', 'gast', 'pasta', 'grpc', 'idna', 'jinja2',
            'joblib', 'clang.cindex', 'markdown_it', 'markupsafe', 'mdurl',
            'ml_dtypes', 'mpmath', 'namex', 'narwhals', 'networkx',
            'opt_einsum', 'optree', 'packaging', 'PIL.Image', 'google.protobuf',
            'pygments', 'dateutil', 'requests', 'rich', 'six', 'sympy',
            'termcolor', 'threadpoolctl', 'typing_extensions', 'tzdata',
            'urllib3', 'wrapt',
        )
        for module in modules:
            importlib.import_module(module)
        print('Imported', len(modules), 'additional package modules')
    """,
}


def check_pins() -> None:
    raw = (ROOT / "requirements.txt").read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    pins = [line.strip() for line in raw.decode(encoding).splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    problems = []
    for pin in pins:
        name, expected = pin.split("==", 1)
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{name}: missing (expected {expected})")
            continue
        if actual != expected:
            problems.append(f"{name}: installed {actual}, expected {expected}")
    if problems:
        raise RuntimeError("Pinned version mismatch:\n" + "\n".join(problems))
    print(f"[PASS] All {len(pins)} pinned versions match requirements.txt", flush=True)


def main() -> None:
    print(f"Python: {sys.version.split()[0]} ({sys.executable})", flush=True)
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Run this check with the project's Python 3.12 environment")
    check_pins()
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    probe_env = dict(os.environ, TF_CPP_MIN_LOG_LEVEL="2", KERAS_BACKEND="tensorflow")
    # Separate processes let each native stack initialize and release its DLLs.
    for label, source in PROBES.items():
        print(f"[CHECK] {label}", flush=True)
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)],
            cwd=ROOT,
            env=probe_env,
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError(f"{label} failed with exit code {result.returncode}")
        print(f"[PASS] {label}", flush=True)
    print("Dependency checks passed.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError) as error:
        print(f"[FAIL] {error}", file=sys.stderr, flush=True)
        raise SystemExit(1) from error
