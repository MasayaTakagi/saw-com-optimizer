"""Lossless typed encoding primitives for Stage 5A-2 journal identities."""
from __future__ import annotations

import base64
import json
import math
import struct
from collections.abc import Mapping
from typing import Any

import numpy as np


class CodecError(ValueError):
    """A value cannot be represented by the versioned lossless codec."""


def _require_plain_dtype(dtype: np.dtype[Any]) -> None:
    if dtype.hasobject:
        raise CodecError("object-dtype values are not supported")
    if dtype.fields is not None or dtype.subdtype is not None:
        raise CodecError("structured and subarray dtypes are not supported")


def _encode(value: Any) -> Any:
    if value is None:
        return {"t": "none"}
    if type(value) is bool:
        return {"t": "bool", "v": value}
    if type(value) is int:
        return {"t": "int", "v": str(value)}
    if type(value) is float:
        return {"t": "f64", "bits_le": struct.pack("<d", value).hex()}
    if type(value) is str:
        return {"t": "str", "v": value}
    if type(value) is bytes:
        return {"t": "bytes", "b64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, np.dtype):
        _require_plain_dtype(value)
        return {"t": "dtype", "v": value.str}
    if isinstance(value, np.ndarray):
        _require_plain_dtype(value.dtype)
        order = "F" if value.flags.f_contiguous and not value.flags.c_contiguous else "C"
        raw = value.tobytes(order=order)
        return {
            "t": "ndarray",
            "dtype": value.dtype.str,
            "shape": list(value.shape),
            "order": order,
            "b64": base64.b64encode(raw).decode("ascii"),
        }
    if isinstance(value, np.generic):
        _require_plain_dtype(value.dtype)
        return {
            "t": "numpy_scalar",
            "dtype": value.dtype.str,
            "hex": np.asarray(value).tobytes().hex(),
        }
    if type(value) is tuple:
        return {"t": "tuple", "v": [_encode(item) for item in value]}
    if type(value) is list:
        return {"t": "list", "v": [_encode(item) for item in value]}
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise CodecError("mapping keys must be strings")
        return {"t": "mapping", "v": [[key, _encode(value[key])] for key in sorted(value)]}
    raise CodecError(f"unsupported typed value: {type(value).__module__}.{type(value).__qualname__}")


def encode_typed(value: Any) -> bytes:
    """Encode supported scalar/container/array values as canonical UTF-8 JSON."""
    try:
        return json.dumps(
            _encode(value), ensure_ascii=True, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, CodecError):
            raise
        raise CodecError(str(exc)) from exc


def _decode(value: Any) -> Any:
    if not isinstance(value, dict) or type(value.get("t")) is not str:
        raise CodecError("malformed typed value")
    tag = value["t"]
    if tag == "none":
        if set(value) != {"t"}:
            raise CodecError("malformed none value")
        return None
    if tag == "bool":
        result = value.get("v")
        if type(result) is not bool or set(value) != {"t", "v"}:
            raise CodecError("malformed bool value")
        return result
    if tag == "int":
        text = value.get("v")
        if type(text) is not str or set(value) != {"t", "v"}:
            raise CodecError("malformed integer value")
        try:
            result = int(text)
        except ValueError as exc:
            raise CodecError("malformed integer token") from exc
        if str(result) != text:
            raise CodecError("non-canonical integer token")
        return result
    if tag == "f64":
        token = value.get("bits_le")
        if type(token) is not str or len(token) != 16 or set(value) != {"t", "bits_le"}:
            raise CodecError("malformed float64 token")
        try:
            return struct.unpack("<d", bytes.fromhex(token))[0]
        except ValueError as exc:
            raise CodecError("malformed float64 token") from exc
    if tag == "str":
        result = value.get("v")
        if type(result) is not str or set(value) != {"t", "v"}:
            raise CodecError("malformed string value")
        return result
    if tag == "dtype":
        token = value.get("v")
        if type(token) is not str or set(value) != {"t", "v"}:
            raise CodecError("malformed NumPy dtype")
        try:
            dtype = np.dtype(token)
        except (TypeError, ValueError) as exc:
            raise CodecError("malformed NumPy dtype") from exc
        _require_plain_dtype(dtype)
        return dtype
    if tag == "bytes":
        token = value.get("b64")
        if type(token) is not str or set(value) != {"t", "b64"}:
            raise CodecError("malformed bytes value")
        try:
            return base64.b64decode(token, validate=True)
        except ValueError as exc:
            raise CodecError("malformed bytes value") from exc
    if tag == "tuple" or tag == "list":
        items = value.get("v")
        if not isinstance(items, list) or set(value) != {"t", "v"}:
            raise CodecError(f"malformed {tag} value")
        decoded = [_decode(item) for item in items]
        return tuple(decoded) if tag == "tuple" else decoded
    if tag == "mapping":
        items = value.get("v")
        if not isinstance(items, list) or set(value) != {"t", "v"}:
            raise CodecError("malformed mapping value")
        result: dict[str, Any] = {}
        previous: str | None = None
        for pair in items:
            if not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not str:
                raise CodecError("malformed mapping entry")
            key = pair[0]
            if previous is not None and key <= previous:
                raise CodecError("mapping keys are duplicate or unsorted")
            previous = key
            result[key] = _decode(pair[1])
        return result
    if tag == "numpy_scalar":
        if set(value) != {"t", "dtype", "hex"} or type(value["dtype"]) is not str or type(value["hex"]) is not str:
            raise CodecError("malformed NumPy scalar")
        try:
            dtype = np.dtype(value["dtype"])
            raw = bytes.fromhex(value["hex"])
        except (TypeError, ValueError) as exc:
            raise CodecError("malformed NumPy scalar") from exc
        try:
            _require_plain_dtype(dtype)
        except CodecError as exc:
            raise CodecError("invalid NumPy scalar dtype") from exc
        if len(raw) != dtype.itemsize:
            raise CodecError("invalid NumPy scalar payload")
        return np.frombuffer(raw, dtype=dtype, count=1)[0]
    if tag == "ndarray":
        if set(value) != {"t", "dtype", "shape", "order", "b64"}:
            raise CodecError("malformed NumPy array")
        if type(value["dtype"]) is not str:
            raise CodecError("invalid NumPy array dtype")
        try:
            dtype = np.dtype(value["dtype"])
        except (TypeError, ValueError) as exc:
            raise CodecError("invalid NumPy array dtype") from exc
        shape = value["shape"]
        order = value["order"]
        try:
            _require_plain_dtype(dtype)
        except CodecError as exc:
            raise CodecError("invalid NumPy array dtype") from exc
        if order not in ("C", "F") or not isinstance(shape, list):
            raise CodecError("invalid NumPy array metadata")
        if any(type(dim) is not int or dim < 0 for dim in shape):
            raise CodecError("invalid NumPy array shape")
        try:
            raw = base64.b64decode(value["b64"], validate=True)
        except ValueError as exc:
            raise CodecError("malformed NumPy array bytes") from exc
        expected = math.prod(shape) * dtype.itemsize
        if len(raw) != expected:
            raise CodecError("NumPy array byte count does not match shape")
        return np.frombuffer(raw, dtype=dtype).copy().reshape(shape, order=order)
    raise CodecError(f"unsupported type tag: {tag}")


def decode_typed(payload: bytes) -> Any:
    """Decode only the canonical byte representation produced by the codec."""
    if type(payload) is not bytes:
        raise CodecError("typed payload must be immutable bytes")
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodecError("malformed typed JSON") from exc
    result = _decode(parsed)
    if encode_typed(result) != payload:
        raise CodecError("typed payload is not in canonical lossless form")
    return result


def canonical_json_bytes(value: Any) -> bytes:
    """Encode a JSON-compatible identity object deterministically."""
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


__all__ = ["CodecError", "canonical_json_bytes", "decode_typed", "encode_typed"]
