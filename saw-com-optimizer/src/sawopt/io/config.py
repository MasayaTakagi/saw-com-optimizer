"""Shared study configuration loading with legacy merge semantics."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml


def deep_update(target, source):
    """Recursively merge mappings, replacing non-mappings with deep copies."""
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_update(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def load_study_config(path):
    """Load a study, its base config, ordered fragments, and COM parameters.

    This intentionally preserves the historical loader contract: the study
    first shallow-updates its base config, fragments are then deep-merged in
    listed order, and exact source text is retained in ``inputs`` for review
    bundles.
    """
    path = Path(path)
    study = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "base_config" in study:
        base_path = path.parent / study["base_config"]
        cfg = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
        cfg.update(study)
    else:
        base_path = path
        cfg = study

    fragment_paths = [path.parent / fragment for fragment in study.get("config_fragments", [])]
    for fragment_path in fragment_paths:
        deep_update(cfg, yaml.safe_load(fragment_path.read_text(encoding="utf-8")) or {})

    com_path = base_path.parent / cfg["com_file"]
    cfg["com"] = yaml.safe_load(com_path.read_text(encoding="utf-8"))
    cfg["inputs"] = {
        path.name: path.read_text(encoding="utf-8"),
        base_path.name: base_path.read_text(encoding="utf-8"),
        com_path.name: com_path.read_text(encoding="utf-8"),
    }
    for fragment_path in fragment_paths:
        cfg["inputs"][fragment_path.name] = fragment_path.read_text(encoding="utf-8")
    return cfg


def cold_seeds(cfg):
    """Return configured seeds, padding to the historical minimum."""
    convergence = cfg.get('convergence', {})
    seeds = [int(seed) for seed in convergence.get('seeds', cfg.get('seeds', []))]
    minimum = int(convergence.get('min_cold_seeds', 5))
    if not seeds:
        raise ValueError('At least one seed is required')
    next_seed = max(seeds) + 1
    while len(set(seeds)) < minimum:
        if next_seed not in seeds:
            seeds.append(next_seed)
        next_seed += 1
    return list(dict.fromkeys(seeds))


def load_experiment_config(path):
    """Resolve a config-driven experiment without changing legacy loading.

    An experiment may point at an existing, fully specified study instance.
    Only its explicit protocol metadata and overrides are added. The
    experiment source itself is also retained in ``inputs`` using a
    project-relative path so the top-level protocol definition is reproducible.
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "study" not in raw:
        return load_study_config(path)
    reference = raw.get("base_config")
    if reference:
        cfg = load_study_config((path.parent / reference).resolve())
    else:
        cfg = load_study_config(path)
    overlay = {key: value for key, value in raw.items()
               if key not in {"base_config", "study"}}
    deep_update(cfg, overlay)
    cfg["study"] = copy.deepcopy(raw["study"])
    project_root = Path(__file__).resolve().parents[3]
    try:
        input_key = path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        input_key = path.resolve().as_posix()
    cfg.setdefault("inputs", {})[input_key] = path.read_text(encoding="utf-8")
    return cfg


__all__ = ["cold_seeds", "deep_update", "load_experiment_config", "load_study_config"]
