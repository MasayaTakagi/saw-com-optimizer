"""Strict frozen Q0 production identity manifest validation.

This module has no physics/provider imports. The canonical manifest stores the
preimages behind the pair identity's aggregate hashes, so callers cannot
authorize a Q0 genesis with opaque, self-asserted digests alone.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass
from typing import Any

from .codec import canonical_json_bytes

PRODUCTION_MANIFEST_SCHEMA = "stage5a2_q0_production_identity_manifest_v1"
PRODUCTION_TOPOLOGIES = frozenset({"P_D", "D_P"})
PRODUCTION_ROOT_SEEDS = frozenset({20261012, 20261013, 20261014})
PRODUCTION_SAMPLER_VERSION = "independent_uniform_rejection_lshade_image_v2"
PRODUCTION_PROTOCOL_ID = "stage5a2-q0-r1-v1"
SEARCH_GRID_POINTS = 1001
SEARCH_GRID_SHA256 = "212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0"
VALIDATION_GRID_POINTS = 9113
VALIDATION_GRID_ID = "2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f"
VALIDATION_GRID_SHA256 = "54c1daf67dd2bb9242f95e638d7bd801db536acc2c7d6f00c1f62a788bead554"
Q0_BOUNDS_CONTRACT_SHA256 = {
    "P_D": "d877825d69b493cf5eb3c86cef3fb4ac440145ff2f8146349c93f585b0247530",
    "D_P": "cc0da54372d92f1db8a9fda7adc1e9ceae33b5945cddcacf923e8eb27ed72fe9",
}
Q0_BOUNDS_LE_F64_HEX = {
    "P_D": "66666666666612409a9999999999154066666666666612409a9999999999154066666666666612409a9999999999154066666666666612409a9999999999154000000000000010400000000000003840000000000000104000000000000038400000000000001440000000000000384000000000000000000000000000000840000000000000000000000000000008400000000000003e4000000000008066400000000000001240666666666666164000000000000024400000000000004e400000000000003e400000000000c06240",
    "D_P": "66666666666612409a9999999999154066666666666612409a9999999999154066666666666612409a9999999999154066666666666612409a9999999999154000000000000010400000000000003840000000000000104000000000000038400000000000001440000000000000384000000000000000000000000000000840000000000000000000000000000008400000000000003e4000000000008066400000000000001240666666666666164000000000000024400000000000004e400000000000003e400000000000c06240",
}
Q0_VARIABLE_NAMES = (
    "wavelength_A_um", "wavelength_B_um", "wavelength_C_um", "reflector_wavelength_um",
    "pairs_A", "pairs_B", "pairs_C", "common_idt_gap_lambda", "reflector_gap_lambda", "aperture_um",
    "resonator_0_wavelength_um", "resonator_0_pairs", "resonator_0_aperture_um",
)
Q0_VARIABLE_UNITS = ("um", "um", "um", "um", "pairs", "pairs", "pairs", "lambda", "lambda", "um",
                     "um", "pairs", "um")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_REQUIRED_SOURCE_PATHS = frozenset({
    "src/sawopt/studies/stage5a2/codec.py",
    "src/sawopt/studies/stage5a2/identity.py",
    "src/sawopt/studies/stage5a2/initialization.py",
    "src/sawopt/studies/stage5a2/rng.py",
    "src/sawopt/design/canonicalization.py",
    "src/sawopt/optimizers/selection.py",
})
_REQUIRED_CONFIG_PATHS = frozenset({
    "configs/studies/hybrid_stage4c_confirmatory.yaml",
    "configs/studies/dms_topology_screening.yaml",
    "configs/models/stage3_7b_r1_normalized_literature_profile.yaml",
})


class ProductionIdentityError(ValueError):
    """A Q0 production identity is incomplete, non-frozen, or inconsistent."""


def _exact_keys(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ProductionIdentityError(f"{name} fields differ from the frozen manifest schema")
    return value


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ProductionIdentityError(f"{name} must be lowercase SHA-256 hex")
    return value


def _hash_record(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def design_space_record_hash(record: dict[str, Any]) -> str:
    """Recompute Q0-R1's design-space hash from its lossless identity record."""
    required = {
        "topology", "variable_names", "bounds_le_f64_hex", "integer_indices", "units", "rounding",
        "design_space_sha256",
    }
    data = _exact_keys(record, required, "design_space")
    topology = data["topology"]
    names, units, indices = data["variable_names"], data["units"], data["integer_indices"]
    bounds_hex = data["bounds_le_f64_hex"]
    if type(topology) is not str or type(names) is not list or type(units) is not list:
        raise ProductionIdentityError("design-space topology/names/units have invalid types")
    if len(names) != 13 or len(units) != 13 or any(type(x) is not str or not x for x in (*names, *units)):
        raise ProductionIdentityError("production design space requires 13 named, unit-bearing variables")
    if type(indices) is not list or any(type(x) is not int for x in indices):
        raise ProductionIdentityError("design-space integer indices are malformed")
    if indices != [4, 5, 6, 11]:
        raise ProductionIdentityError("Q0 production integer indices must be [4, 5, 6, 11]")
    if type(bounds_hex) is not str or len(bounds_hex) != 13 * 2 * 16:
        raise ProductionIdentityError("production bounds must encode exactly 13 binary64 pairs")
    try:
        raw = bytes.fromhex(bounds_hex)
    except ValueError as exc:
        raise ProductionIdentityError("production bounds are not valid hexadecimal") from exc
    if raw.hex() != bounds_hex:
        raise ProductionIdentityError("production bounds hex must be lowercase and canonical")
    values = struct.unpack("<26d", raw)
    rows = [values[index:index + 2] for index in range(0, len(values), 2)]
    if any(not (lo < hi) for lo, hi in rows):
        raise ProductionIdentityError("production bounds must be ordered")
    if data["rounding"] != "floor(x+0.5)":
        raise ProductionIdentityError("Q0 design-space rounding identity must be floor(x+0.5)")
    payload = {
        "topology": topology,
        "variable_names": names,
        "active_bounds_f64be": [
            [struct.pack(">d", number).hex() for number in row] for row in rows
        ],
        "integer_indices": indices,
        "units": units,
        "rounding": "floor(x+0.5)",
    }
    result = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    if data["design_space_sha256"] != result:
        raise ProductionIdentityError("design-space hash does not bind its exact names/bounds/indices/units")
    return result


@dataclass(frozen=True, slots=True)
class Q0ProductionIdentityManifest:
    """A canonical, auditable Q0 identity preimage bound to one pair record."""

    canonical_bytes: bytes

    @property
    def record(self) -> dict[str, Any]:
        """Return a detached parse so callers cannot mutate validated identity state."""
        return json.loads(self.canonical_bytes.decode("utf-8"))

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Q0ProductionIdentityManifest":
        canonical = canonical_json_bytes(record)
        instance = cls(canonical)
        instance.validate()
        return instance

    @classmethod
    def from_bytes(cls, payload: bytes) -> "Q0ProductionIdentityManifest":
        if type(payload) is not bytes:
            raise ProductionIdentityError("production manifest payload must be immutable bytes")
        try:
            record = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductionIdentityError("production manifest JSON is malformed") from exc
        if canonical_json_bytes(record) != payload:
            raise ProductionIdentityError("production manifest is not canonical JSON")
        return cls(payload).validate()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def validate(self) -> "Q0ProductionIdentityManifest":
        keys = {
            "schema", "protocol_id", "study_role", "topology", "root_seed", "source",
            "configuration", "evaluator", "grids", "design_space", "environment", "sampler",
            "common_contract", "arms", "schemas",
        }
        record = _exact_keys(self.record, keys, "production manifest")
        if record["schema"] != PRODUCTION_MANIFEST_SCHEMA or record["protocol_id"] != PRODUCTION_PROTOCOL_ID:
            raise ProductionIdentityError("production manifest schema or protocol is not the frozen Q0 version")
        if record["study_role"] != "stage5a2_matched_optimizer_comparison":
            raise ProductionIdentityError("production manifest has the wrong Q0 study role")
        topology, root_seed = record["topology"], record["root_seed"]
        if topology not in PRODUCTION_TOPOLOGIES or type(root_seed) is not int or root_seed not in PRODUCTION_ROOT_SEEDS:
            raise ProductionIdentityError("Q0 production permits only P_D/D_P and the three frozen roots")

        source = _exact_keys(record["source"], {
            "source_commit_sha", "clean_tree", "computation_sources",
        }, "source")
        if type(source["source_commit_sha"]) is not str or _GIT_SHA.fullmatch(source["source_commit_sha"]) is None:
            raise ProductionIdentityError("production source commit must be a full Git object ID")
        if source["clean_tree"] is not True:
            raise ProductionIdentityError("Q0 production identity requires a clean source tree")
        source_rows = source["computation_sources"]
        if type(source_rows) is not list or any(
            type(row) is not list or len(row) != 2 or type(row[0]) is not str for row in source_rows
        ):
            raise ProductionIdentityError("computation-source fingerprints are malformed")
        source_map = {row[0]: _sha(row[1], f"source fingerprint {row[0]}") for row in source_rows}
        if len(source_map) != len(source_rows) or not _REQUIRED_SOURCE_PATHS <= set(source_map):
            raise ProductionIdentityError("source fingerprints must uniquely cover all required numerical source files")

        configuration = _exact_keys(record["configuration"], {
            "raw_config_sha256s", "effective_config",
        }, "configuration")
        config_rows = configuration["raw_config_sha256s"]
        if type(config_rows) is not list or any(
            type(row) is not list or len(row) != 2 or type(row[0]) is not str for row in config_rows
        ):
            raise ProductionIdentityError("raw configuration fingerprints are malformed")
        config_map = {row[0]: _sha(row[1], f"config fingerprint {row[0]}") for row in config_rows}
        if len(config_map) != len(config_rows) or not _REQUIRED_CONFIG_PATHS <= set(config_map):
            raise ProductionIdentityError("raw config fingerprints must cover the frozen model/study inputs")
        effective = _exact_keys(configuration["effective_config"], {
            "material", "profile_id", "dms_topology", "source_impedance_ohm", "load_impedance_ohm",
            "specification", "geometry_constraints", "layout_constraints", "design_space_contract_sha256",
            "search_budget", "validation_grid_id", "population_size", "initialization_sampler",
        }, "effective_config")
        if (
            effective["material"] != "MLIT"
            or effective["profile_id"] != "LI2024_42YX_LT_METAL_UNSPECIFIED_T25"
            or effective["dms_topology"] != "T1_SYMMETRIC_5IDT"
            or effective["source_impedance_ohm"] != 50.0
            or effective["load_impedance_ohm"] != 50.0
            or effective["search_budget"] != 4096
            or effective["validation_grid_id"] != VALIDATION_GRID_ID
            or effective["population_size"] != 234
            or effective["initialization_sampler"] != PRODUCTION_SAMPLER_VERSION
        ):
            raise ProductionIdentityError("effective configuration differs from the frozen Stage 5A-2 conditions")
        _sha(effective["design_space_contract_sha256"], "design_space_contract_sha256")
        if effective["specification"] != {
            "passband_mhz": [758.0, 803.0], "il_db": 3.0, "ripple_db": 2.0, "vswr": 2.5,
            "stopbands_mhz_db": [[10.0, 700.0, 20.0], [703.0, 748.0, 32.0],
                                  [832.0, 862.0, 30.0], [880.0, 915.0, 30.0]],
        }:
            raise ProductionIdentityError("effective specification differs from the frozen Stage 4C contract")
        if effective["geometry_constraints"] != {
            "max_length_um": 750, "max_width_um": 250,
            "min_electrode_width_um": 0.8, "min_electrode_gap_um": 0.8, "max_electrodes": 500,
        }:
            raise ProductionIdentityError("effective geometry constraints differ from the frozen Q0 contract")
        if effective["layout_constraints"] != {
            "model": "hypothetical_separate_rows", "die_um": [900, 700],
            "length_margin_um": 60, "width_margin_um": 60,
            "max_total_electrodes": 500, "qualification_only": True,
        }:
            raise ProductionIdentityError("effective layout constraints differ from the frozen Q0 contract")
        if _hash_record(configuration) != _hash_record(record["configuration"]):
            raise ProductionIdentityError("configuration preimage is not canonical")

        evaluator = _exact_keys(record["evaluator"], {"model_id", "implementation_sha256", "computation_sha256"}, "evaluator")
        if evaluator["model_id"] != "Stage4C_MLIT_T1" or _sha(evaluator["implementation_sha256"], "evaluator implementation") is None:
            raise ProductionIdentityError("evaluator identity is not the frozen MLIT/T1 evaluator")
        _sha(evaluator["computation_sha256"], "evaluator computation fingerprint")

        grids = _exact_keys(record["grids"], {"search", "validation"}, "grids")
        search = _exact_keys(grids["search"], {"point_count", "content_sha256"}, "search grid")
        validation = _exact_keys(grids["validation"], {"point_count", "grid_id", "content_sha256"}, "validation grid")
        if search != {"point_count": SEARCH_GRID_POINTS, "content_sha256": SEARCH_GRID_SHA256}:
            raise ProductionIdentityError("search grid differs from the frozen 1,001-point grid")
        if validation != {
            "point_count": VALIDATION_GRID_POINTS, "grid_id": VALIDATION_GRID_ID,
            "content_sha256": VALIDATION_GRID_SHA256,
        }:
            raise ProductionIdentityError("common validation grid differs from the frozen 9,113-point grid")

        design = _exact_keys(record["design_space"], {
            "topology", "dimension", "variable_names", "bounds_le_f64_hex", "integer_indices", "units",
            "rounding", "design_space_sha256", "contract_sha256",
        }, "design_space")
        if design["topology"] != topology or design["dimension"] != 13:
            raise ProductionIdentityError("production design-space topology/dimension mismatch")
        if design["contract_sha256"] != Q0_BOUNDS_CONTRACT_SHA256[topology]:
            raise ProductionIdentityError("design-space bounds contract is not the frozen topology contract")
        if design["bounds_le_f64_hex"] != Q0_BOUNDS_LE_F64_HEX[topology]:
            raise ProductionIdentityError("production bounds differ from the exact frozen topology bounds")
        if design["variable_names"] != list(Q0_VARIABLE_NAMES) or design["units"] != list(Q0_VARIABLE_UNITS):
            raise ProductionIdentityError("production variable names/units differ from the frozen design vector")
        computed_space = design_space_record_hash({
            key: design[key] for key in (
                "topology", "variable_names", "bounds_le_f64_hex", "integer_indices", "units",
                "rounding", "design_space_sha256",
            )
        })
        if computed_space != design["design_space_sha256"]:
            raise ProductionIdentityError("frozen design-space identity is inconsistent")
        if effective["design_space_contract_sha256"] != design["contract_sha256"]:
            raise ProductionIdentityError("effective config and design-space contract fingerprints disagree")

        environment = _exact_keys(record["environment"], {
            "python", "numpy", "scipy", "platform", "blas", "thread_settings", "lock_sha256",
        }, "environment")
        for key in ("python", "numpy", "scipy", "platform", "blas"):
            if type(environment[key]) is not str or not environment[key]:
                raise ProductionIdentityError(f"environment {key} identity is required")
        if type(environment["thread_settings"]) is not dict or not environment["thread_settings"]:
            raise ProductionIdentityError("BLAS/OpenMP thread settings are required")
        _sha(environment["lock_sha256"], "dependency lock fingerprint")

        sampler = _exact_keys(record["sampler"], {
            "version", "seed_protocol", "seed_derivation_sha256", "bit_generator", "state_schema",
            "population_size", "max_draws", "transformation_sha256",
        }, "sampler")
        if (
            sampler["version"] != PRODUCTION_SAMPLER_VERSION
            or sampler["seed_protocol"] != PRODUCTION_PROTOCOL_ID
            or sampler["bit_generator"] != "PCG64"
            or sampler["state_schema"] != "stage5a2_pcg64_state_v1"
            or sampler["population_size"] != 234 or sampler["max_draws"] != 10000
        ):
            raise ProductionIdentityError("sampler/seed/generator contract differs from Q0")
        _sha(sampler["seed_derivation_sha256"], "seed derivation fingerprint")
        _sha(sampler["transformation_sha256"], "sampler transformation fingerprint")

        common = _exact_keys(record["common_contract"], {
            "search_budget", "terminal_horizon", "watchdog_proposals", "topology", "root_seed",
            "comparator_id", "comparator_sha256", "canonicalizer_sha256", "rounding",
        }, "common_contract")
        if (
            common["search_budget"] != 4096 or common["terminal_horizon"] != 4096
            or common["watchdog_proposals"] != 65536 or common["topology"] != topology
            or common["root_seed"] != root_seed or common["comparator_id"] != "GeometryFirstComparator.rank_key"
            or common["rounding"] != "floor(x+0.5)"
        ):
            raise ProductionIdentityError("common comparison contract differs from Q0")
        for key in ("comparator_sha256", "canonicalizer_sha256"):
            _sha(common[key], key)

        arms = _exact_keys(record["arms"], {"lshade", "controlled_de"}, "arms")
        lshade = _exact_keys(arms["lshade"], {
            "optimizer_id", "version", "resolved_settings", "seed_role", "budget", "terminal_horizon",
        }, "L-SHADE arm")
        de = _exact_keys(arms["controlled_de"], {
            "optimizer_id", "version", "resolved_settings", "seed_role", "budget", "terminal_horizon",
        }, "controlled-DE arm")
        if (
            lshade["optimizer_id"] != "L-SHADE" or de["optimizer_id"] != "DE/rand/1/bin"
            or lshade["seed_role"] != "optimizer_lshade" or de["seed_role"] != "optimizer_controlled_de"
            or any(arm["budget"] != 4096 or arm["terminal_horizon"] != 4096 for arm in (lshade, de))
            or not isinstance(lshade["resolved_settings"], dict)
            or not isinstance(de["resolved_settings"], dict)
        ):
            raise ProductionIdentityError("optimizer arms differ from the frozen complete-package comparison")
        if lshade["resolved_settings"].get("initial_population") != 234 or lshade["resolved_settings"].get("min_population") != 4:
            raise ProductionIdentityError("L-SHADE settings differ from the frozen cold-start package")
        if de["resolved_settings"].get("population_size") != 234 or de["resolved_settings"].get("F") != 0.5 or de["resolved_settings"].get("CR") != 0.9:
            raise ProductionIdentityError("controlled-DE settings differ from the frozen operator")

        schemas = _exact_keys(record["schemas"], {
            "candidate", "journal", "canonical_key", "rank", "rng_call", "pcg64_state",
            "optimizer_state", "outer_envelope",
        }, "schema identities")
        expected_schemas = {
            "candidate": "stage5a2_candidate_record_v1", "journal": "stage5a2_txn_journal_v1",
            "canonical_key": "f64be_tuple_v1", "rng_call": "stage5a2_rng_call_v1",
            "pcg64_state": "stage5a2_pcg64_state_v1",
        }
        if any(schemas.get(key) != value for key, value in expected_schemas.items()):
            raise ProductionIdentityError("identity manifest contains an unsupported record/codec schema")
        if any(type(schemas[key]) is not str or not schemas[key] for key in schemas):
            raise ProductionIdentityError("all optimizer/rank/envelope schema versions are required")
        return self

    def verify_pair_fields(self, pair: Any) -> None:
        """Verify all aggregate identity fields against this complete preimage."""
        record = self.record
        expected = {
            "protocol_id": record["protocol_id"],
            "source_commit_sha": record["source"]["source_commit_sha"],
            "config_sha256": _hash_record(record["configuration"]),
            "evaluator_sha256": _hash_record(record["evaluator"]),
            "grid_sha256": _hash_record(record["grids"]),
            "environment_sha256": _hash_record(record["environment"]),
            "topology": record["topology"],
            "root_seed": record["root_seed"],
            "design_space_sha256": record["design_space"]["design_space_sha256"],
            "sampler_version": record["sampler"]["version"],
            "arm_config_hashes": tuple(
                (role, _hash_record(record["arms"][role])) for role in ("lshade", "controlled_de")
            ),
        }
        for field, value in expected.items():
            actual = getattr(pair, field)
            if actual != value:
                raise ProductionIdentityError(f"pair identity {field} does not match its complete manifest preimage")
        if pair.identity_scope != "q0_production" or pair.production_manifest_json != self.canonical_bytes:
            raise ProductionIdentityError("pair identity is not bound to this exact production manifest")

    def metadata_record(self) -> dict[str, Any]:
        return self.record["design_space"]


__all__ = [
    "PRODUCTION_MANIFEST_SCHEMA", "ProductionIdentityError", "Q0ProductionIdentityManifest",
    "design_space_record_hash",
]
