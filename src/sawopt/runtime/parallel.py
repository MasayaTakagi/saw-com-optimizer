"""Shared process-environment helpers for numerical worker pools."""
from __future__ import annotations

import os
from contextlib import contextmanager


@contextmanager
def single_blas_thread_environment(threads=1):
    """Temporarily cap the BLAS/OpenMP thread count for one worker."""
    names = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ[name] = str(int(threads))
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


__all__ = ["single_blas_thread_environment"]
