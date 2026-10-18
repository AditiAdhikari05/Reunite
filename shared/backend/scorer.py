"""
scorer.py - the match scorer: turns the pair features into a 0-1 score. The deployed model is a single layer
(logistic regression); the code supports deeper networks too, which is where the accelerator pays off.

Training happens on the CPU with scikit-learn (see train.py). IBM's own guidance for TensorFlow on Z is
"train anywhere, deploy on IBM Z" and to switch the accelerator off for training. Inference has two paths:

  * numpy      - works everywhere, used for small batches (one report vs all found people)
  * TensorFlow - uses the IBM zDNN plugin, so the dense layers run on the Telum on-chip AI accelerator.
                 Used for big batches (re-scoring every report against every found person), but only when a
                 start-up timing check shows it is faster than numpy for this model (backend="tf" forces it).
                 Set NNPA_DEVICES=0 before starting Python to force the TensorFlow path onto the plain CPU.
"""
import os
import time

import numpy as np

TF_BATCH = 8192          # fixed batch size so TensorFlow traces the graph once (same shape as our chip test)
TF_MIN_ROWS = 4096       # below this many rows, numpy on the CPU is faster than going through the accelerator


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


class NumpyMLP:
    def __init__(self, layers):
        self.layers = [(np.asarray(W, np.float32), np.asarray(b, np.float32)) for W, b in layers]
        self.n_in = self.layers[0][0].shape[0]

    def predict(self, X):
        X = np.asarray(X, np.float32).reshape(-1, self.n_in)
        out = np.empty(len(X), np.float32)
        for i in range(0, len(X), 16384):
            h = X[i:i + 16384]
            for W, b in self.layers[:-1]:
                h = np.maximum(h @ W + b, 0)
            W, b = self.layers[-1]
            out[i:i + 16384] = _sigmoid(h @ W + b)[:, 0]
        return out


class TfMLP:
    """The same network built from Keras Dense layers, so the IBM plugin can map it onto the accelerator."""

    def __init__(self, layers):
        import tensorflow as tf
        self.tf = tf
        self.n_in = layers[0][0].shape[0]
        stack = [tf.keras.Input(shape=(self.n_in,))]
        for k, (W, _) in enumerate(layers):
            last = k == len(layers) - 1
            stack.append(tf.keras.layers.Dense(W.shape[1], activation="sigmoid" if last else "relu"))
        model = tf.keras.Sequential(stack)
        model.set_weights([a for W, b in layers for a in (np.asarray(W, np.float32), np.asarray(b, np.float32))])

        @tf.function
        def run(x):
            return model(x, training=False)
        self._run = run
        self._run(tf.zeros((TF_BATCH, self.n_in), tf.float32)).numpy()      # trace + warm up once

    def predict(self, X):
        tf = self.tf
        X = np.asarray(X, np.float32).reshape(-1, self.n_in)
        out = np.empty(len(X), np.float32)
        for i in range(0, len(X), TF_BATCH):
            chunk = X[i:i + TF_BATCH]
            m = len(chunk)
            if m < TF_BATCH:
                chunk = np.vstack([chunk, np.zeros((TF_BATCH - m, self.n_in), np.float32)])
            out[i:i + m] = self._run(tf.constant(chunk)).numpy()[:m, 0]
        return out


def device_mode(tf_active):
    if not tf_active:
        return "numpy on CPU"
    off = os.environ.get("NNPA_DEVICES", "").strip().lower() in ("0", "false")
    return "TensorFlow, accelerator OFF (CPU)" if off else "TensorFlow, IBM Z AI accelerator ON"


class Scorer:
    """Loads weights from models/scorer.npz and picks the right inference path for the batch size."""

    def __init__(self, npz_path, backend="auto", log=print):
        z = np.load(npz_path)
        n = int(z["n_layers"])
        layers = [(z[f"W{i}"], z[f"b{i}"]) for i in range(n)]
        self.numpy = NumpyMLP(layers)
        self.tf = None
        self.tf_error = None
        self.tf_faster = False
        self.probe_ms = {}
        self.forced = backend == "tf"
        if backend in ("auto", "tf"):
            try:
                self.tf = TfMLP(layers)
                probe = np.random.RandomState(0).rand(TF_BATCH, self.numpy.n_in).astype(np.float32)
                diff = float(np.abs(self.tf.predict(probe) - self.numpy.predict(probe)).max())
                if diff > 0.05:
                    raise RuntimeError(f"TensorFlow and numpy outputs disagree (max diff {diff:.3f})")
                best = {}
                for name, fn in (("numpy", self.numpy.predict), ("tensorflow", self.tf.predict)):
                    runs = []
                    for _ in range(3):
                        t0 = time.time(); fn(probe); runs.append(time.time() - t0)
                    best[name] = min(runs)
                self.probe_ms = {k: round(v * 1000, 2) for k, v in best.items()}
                self.tf_faster = best["tensorflow"] < best["numpy"]
                log(f"[scorer] TensorFlow path ready (max diff vs numpy {diff:.4f}); timing on {TF_BATCH} pairs: "
                    f"numpy {self.probe_ms['numpy']} ms, tensorflow {self.probe_ms['tensorflow']} ms -> "
                    f"{'tensorflow' if (self.tf_faster or self.forced) else 'numpy'} used for big batches")
            except Exception as e:                      # TensorFlow missing, broken or inaccurate -> numpy only
                self.tf, self.tf_error = None, f"{type(e).__name__}: {e}"
                log(f"[scorer] TensorFlow path unavailable, using numpy. Reason: {self.tf_error}")
        self.last = {}

    def predict(self, X):
        """X: (n, n_features) -> (n,) scores in 0..1. Records timing in self.last."""
        t = time.time()
        use_tf = self.tf is not None and (self.tf_faster or self.forced) and len(X) >= TF_MIN_ROWS
        out = (self.tf if use_tf else self.numpy).predict(X)
        dt = time.time() - t
        self.last = {"rows": int(len(X)), "seconds": round(dt, 4), "rows_per_sec": int(len(X) / max(dt, 1e-9)),
                     "mode": device_mode(use_tf)}
        return out

    def info(self):
        return {"tensorflow_available": self.tf is not None, "tensorflow_error": self.tf_error,
                "big_batches_use": "tensorflow" if self.tf is not None and (self.tf_faster or self.forced) else "numpy",
                "startup_timing_ms_per_8192_pairs": self.probe_ms,
                "layers": [list(W.shape) for W, _ in self.numpy.layers]}


def save_weights(path, layers):
    arrs = {"n_layers": np.array(len(layers))}
    for i, (W, b) in enumerate(layers):
        arrs[f"W{i}"], arrs[f"b{i}"] = np.asarray(W, np.float32), np.asarray(b, np.float32)
    np.savez(path, **arrs)
