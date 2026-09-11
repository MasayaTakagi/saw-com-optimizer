"""Incremental frequency-response caching and diagnostic aggregation."""
from __future__ import annotations

import time

import numpy as np


def aggregate_diagnostics(diagnostics):
    """Merge diagnostics from disjoint frequency batches conservatively."""
    items = [dict(item) for item in diagnostics if item]
    if not items:
        return {}
    keys = set().union(*(item for item in items))
    minimum_keys = {"min_conductance_eigenvalue"}
    maximum_keys = {
        "reciprocity_error", "max_acoustic_solve_residual",
        "max_acoustic_condition_number", "admittance_scale",
        "passivity_tolerance", "reciprocity_tolerance",
    }
    frequency_for = {
        "min_conductance_eigenvalue": "worst_conductance_frequency_hz",
        "reciprocity_error": "worst_reciprocity_frequency_hz",
        "max_acoustic_solve_residual": "worst_acoustic_residual_frequency_hz",
        "max_acoustic_condition_number": "worst_acoustic_condition_frequency_hz",
    }
    frequency_keys = set(frequency_for.values())
    result = {}
    for key in sorted(keys):
        values = [item[key] for item in items if key in item]
        if not values:
            continue
        if key in frequency_keys:
            continue
        if (isinstance(values[0], (bool, np.bool_)) or key.startswith(("has_", "nonfinite", "failure"))
                or key.endswith("_failure")):
            result[key] = bool(any(bool(value) for value in values))
            continue
        numeric = all(np.isscalar(value) and np.isreal(value) for value in values)
        if key in minimum_keys and numeric:
            index = int(np.argmin(np.asarray(values, dtype=float)))
            result[key] = float(values[index])
        elif key in maximum_keys and numeric:
            index = int(np.argmax(np.asarray(values, dtype=float)))
            result[key] = float(values[index])
        elif numeric:
            result[key] = float(max(values)) if "tolerance" in key else values[0]
        else:
            result[key] = values[0]

        controlling_key = frequency_for.get(key)
        if controlling_key and controlling_key in keys:
            control_values = [
                item.get(controlling_key) for item in items
                if key in item and controlling_key in item
            ]
            if control_values:
                if key in minimum_keys:
                    control_index = int(np.argmin([
                        item[key] for item in items
                        if key in item and controlling_key in item
                    ]))
                else:
                    control_index = int(np.argmax([
                        item[key] for item in items
                        if key in item and controlling_key in item
                    ]))
                result[controlling_key] = float(control_values[control_index])
    return result


class IncrementalFrequencyCache:
    """Cache a fixed candidate's frequency-point response without approximation."""

    def __init__(self, evaluator):
        self.evaluator = evaluator
        self._values = {}
        self._metadata = {}
        self._diagnostic_batches = []
        self.solved_points = 0
        self.last_evaluation_wall_time_s = 0.0

    @property
    def cached_frequencies(self):
        return np.asarray(sorted(self._values), dtype=float)

    def evaluate(self, frequencies_hz):
        frequencies = np.unique(np.asarray(frequencies_hz, dtype=float))
        if frequencies.ndim != 1 or len(frequencies) == 0:
            raise ValueError("frequencies must be a non-empty one-dimensional array")
        missing = np.asarray([x for x in frequencies if float(x) not in self._values])
        self.last_evaluation_wall_time_s = 0.0
        if len(missing):
            started = time.time()
            payload = self.evaluator(missing)
            self.last_evaluation_wall_time_s = time.time() - started
            if not isinstance(payload, dict):
                raise TypeError("Incremental evaluator must return a mapping")
            for key, value in payload.items():
                if key == "_diagnostics" and isinstance(value, dict):
                    self._diagnostic_batches.append(value)
                    self._metadata[key] = aggregate_diagnostics(self._diagnostic_batches)
                    continue
                array = np.asarray(value)
                if array.ndim and array.shape[0] == len(missing):
                    if key == "frequencies_hz":
                        continue
                    for index, frequency in enumerate(missing):
                        self._values.setdefault(float(frequency), {})[key] = array[index]
                else:
                    self._metadata[key] = value
            self.solved_points += len(missing)

        result = {"frequencies_hz": frequencies.copy()}
        keys = set(self._metadata)
        for value in self._values.values():
            keys.update(value)
        for key in sorted(keys):
            if key in self._metadata and key not in self._values.get(float(frequencies[0]), {}):
                result[key] = self._metadata[key]
                continue
            rows = []
            for frequency in frequencies:
                if float(frequency) not in self._values or key not in self._values[float(frequency)]:
                    raise ValueError(f"Frequency evaluator omitted array value {key!r}")
                rows.append(self._values[float(frequency)][key])
            result[key] = np.asarray(rows)
        return result


__all__ = ["aggregate_diagnostics", "IncrementalFrequencyCache"]
