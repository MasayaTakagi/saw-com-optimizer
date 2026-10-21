from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from sawopt.design.canonicalization import canonicalize_hybrid_vector
from sawopt.studies.stage5a2.codec import CodecError, decode_typed, encode_typed
from sawopt.studies.stage5a2.identity import (
    ARM_ROLES,
    CellIdentity,
    GenesisCoordinator,
    GenesisError,
    PairIdentity,
)
from sawopt.studies.stage5a2.initialization import (
    DesignSpaceMetadata,
    InitializationError,
    InitializationGateError,
    POPULATION_SIZE,
    attach_population,
    canonical_key_tokens,
    dispatch_initial_evaluation,
    persist_both_preflight_certificates,
    preflight_controlled_de,
    preflight_lshade,
    require_both_preflight_certificates,
    sample_initial_population,
)
from sawopt.studies.stage5a2.journal import JournalError, SQLiteJournal
from sawopt.studies.stage5a2.rng import (
    RNGCallIdentity,
    RNGCallService,
    RNGProtocolError,
    derive_seed32,
    design_space_sha256,
    pcg64_state,
    restore_pcg64_state,
)

ROOT = Path(__file__).resolve().parents[3]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _metadata(topology: str = "P_D") -> DesignSpaceMetadata:
    bounds = np.asarray([[0.0, 1.0], [0.0, 1.0]], dtype=np.float64)
    names = ("x", "y")
    indices: tuple[int, ...] = ()
    units = ("unitless", "unitless")
    digest = design_space_sha256(topology, names, bounds, indices, units)
    return DesignSpaceMetadata(
        topology, names, tuple(tuple(float(value) for value in row) for row in bounds), indices, units, digest,
    )


def _pair(metadata: DesignSpaceMetadata | None = None) -> PairIdentity:
    return PairIdentity(
        pair_journal_uuid="00000000-0000-4000-8000-000000000001",
        protocol_id="stage5a2-q0-r1-v1",
        source_commit_sha=_digest("source"),
        config_sha256=_digest("config"),
        evaluator_sha256=_digest("evaluator"),
        grid_sha256=_digest("grid"),
        environment_sha256=_digest("environment"),
        topology=metadata.topology if metadata else "P_D",
        root_seed=20261012,
        design_space_sha256=metadata.design_space_sha256 if metadata else _digest("space"),
        sampler_version="independent_uniform_rejection_lshade_image_v2",
        arm_config_hashes=(("lshade", _digest("lshade-config")), ("controlled_de", _digest("de-config"))),
        cell_journal_uuids=(
            ("lshade", "00000000-0000-4000-8000-000000000002"),
            ("controlled_de", "00000000-0000-4000-8000-000000000003"),
        ),
    )


def _cell_identity(pair: PairIdentity, role: str) -> CellIdentity:
    return CellIdentity(
        cell_journal_uuid=dict(pair.cell_journal_uuids)[role],
        pair_journal_uuid=pair.pair_journal_uuid,
        pair_identity_id=pair.identity_id,
        pair_identity_sha256=pair.identity_sha256,
        role=role,
        arm_config_sha256=dict(pair.arm_config_hashes)[role],
        environment_sha256=pair.environment_sha256,
    )


def _coordinator(tmp_path: Path, pair: PairIdentity):
    coordinator = GenesisCoordinator(
        tmp_path / "pair.sqlite", (tmp_path / "lshade.sqlite", tmp_path / "de.sqlite"),
    )
    cells = tuple(_cell_identity(pair, role) for role in ARM_ROLES)
    return coordinator, cells


def _normalize(metadata):
    bounds = metadata.bounds_array()
    low, high = bounds[:, 0], bounds[:, 1]
    return lambda values: np.clip((np.asarray(values, dtype=float) - low) / (high - low), 0.0, 1.0)


def _physical(metadata):
    bounds = metadata.bounds_array()
    low, high = bounds[:, 0], bounds[:, 1]
    return lambda values: low + np.clip(np.asarray(values, dtype=float), 0.0, 1.0) * (high - low)


def _canonicalizer(metadata):
    return lambda values: canonicalize_hybrid_vector(
        values, bounds=metadata.bounds_array(), integer_indices=metadata.integer_indices,
        dimension=metadata.dimension, topology=metadata.topology,
    )


def _seed(pair):
    return derive_seed32(
        role="common_init", root_seed=pair.root_seed, topology=pair.topology,
        design_space_hash=pair.design_space_sha256,
    )


class _ScriptedRNG:
    def __init__(self, vectors, journal, seed):
        self.vectors = list(vectors)
        self.calls = []
        self.journal = journal
        self.generator = np.random.Generator(np.random.PCG64(seed))
        self.initial_state = pcg64_state(self.generator)

    def call(self, identity, method, low, high):
        assert method == "uniform"
        assert identity.ordinal == len(self.calls)
        self.calls.append(identity)
        return np.asarray(self.vectors[len(self.calls) - 1], dtype=np.float64)


class _MemoryJournal:
    def __init__(self, journal_uuid):
        self.journal_uuid = journal_uuid
        self.owner_kind = "pair"
        self._events = {}

    def append_event(self, event_id, event_type, payload):
        old = self._events.get(event_id)
        if old is not None:
            assert old == (event_type, payload)
        else:
            self._events[event_id] = (event_type, payload)
        return SimpleNamespace(event_hash=_digest(event_id))


def test_legacy_golden_public_delegate_and_leaf_exactly_match_in_fresh_processes():
    verifier = ROOT / "scripts/verify_stage5a2_canonicalization_golden.py"
    for mode in ("public", "leaf"):
        result = subprocess.run(
            [sys.executable, str(verifier), "--mode", mode], cwd=ROOT,
            check=True, capture_output=True, text=True,
        )
        payload = json.loads(result.stdout)
        assert payload["cases_passed"] == 92
        assert payload["fixture_sha256"] == "3763c5746f4bf800a54f310aeeb94f493520fc0962505b1eed85d3c32b589aa2"
        assert payload["source_commit_sha"] == "f32b8f8dac928f21c567b34593b1ed227a4c9c9e"


def test_leaf_normal_import_has_no_physics_problem_or_production_imports():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_stage5a2_pure_leaf_import.py")],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    assert json.loads(result.stdout)["forbidden_imports"] == []


def test_all_q1a_runtime_modules_import_without_physics_or_orchestration():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_stage5a2_foundation_imports.py")],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["forbidden_imports"] == []
    assert "sawopt.studies.stage5a2.initialization" in payload["modules_imported"]


def test_seed_derivation_matches_all_frozen_role_topology_root_vectors():
    fixture = json.loads((ROOT / "tests/fixtures/stage5a2/seed_derivation_golden.json").read_text())
    assert fixture["schema"] == "stage5a2_seed_derivation_golden_v1"
    assert len(fixture["records"]) == 18
    for row in fixture["records"]:
        assert derive_seed32(
            role=row["role"], root_seed=row["root_seed"], topology=row["topology"],
            design_space_hash=fixture["design_space_sha256"],
        ) == row["seed32"]


def test_q0_design_space_contract_matches_frozen_stage4a_configuration():
    import yaml

    fixture_path = ROOT / "tests/fixtures/stage5a2/q0_design_space_contract.json"
    fixture = json.loads(fixture_path.read_text())
    config_path = ROOT / "configs/studies/hybrid_stage4a_qualification.yaml"
    base_path = ROOT / "configs/studies/dms_topology_screening.yaml"
    for path in (config_path, base_path):
        relative = str(path.relative_to(ROOT))
        assert fixture["sources"][relative] == hashlib.sha256(path.read_bytes()).hexdigest()
    config, base = yaml.safe_load(config_path.read_text()), yaml.safe_load(base_path.read_text())
    assert fixture["schema"] == "stage5a2_q0_design_space_contract_v1"
    assert [item["topology"] for item in fixture["topologies"]] == config["hybrid"]["supported_topologies"]
    dms = np.asarray(base["dms_topology"]["topologies"]["T1_SYMMETRIC_5IDT"]["bounds"]["active"], dtype="<f8")
    dms[9] = np.asarray(base["dms_topology"]["materials"]["MLIT"]["aperture_bounds_um"], dtype="<f8")
    resonator = np.asarray(config["hybrid"]["resonator_bounds"], dtype="<f8")
    resonator_count = {"D": 0, "P_D": 1, "D_P": 1, "P_D_P": 2}
    for record in fixture["topologies"]:
        count = resonator_count[record["topology"]]
        expected_bounds = np.vstack([dms, *([resonator] * count)]).astype("<f8", copy=False)
        expected_indices = (4, 5, 6) + tuple(10 + index * 3 + 1 for index in range(count))
        assert record["dimension"] == len(expected_bounds)
        assert record["integer_indices"] == list(expected_indices)
        assert record["bounds_le_f64_hex"] == expected_bounds.tobytes().hex()
        body = {key: value for key, value in record.items() if key != "contract_sha256"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        assert record["contract_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_design_space_hash_binds_metadata_and_normalizes_signed_zero():
    metadata = _metadata()
    assert canonical_key_tokens(np.asarray([-0.0])) != canonical_key_tokens(np.asarray([0.0]))
    assert metadata.design_space_sha256 == design_space_sha256(
        metadata.topology, metadata.variable_names, metadata.bounds_array(),
        metadata.integer_indices, metadata.units,
    )
    with pytest.raises(ValueError, match="does not match frozen metadata"):
        DesignSpaceMetadata(
            "P_D", metadata.variable_names, metadata.bounds, metadata.integer_indices,
            metadata.units, _digest("wrong-bound-identity"),
        )


def test_lossless_typed_codec_preserves_values_types_and_array_layout():
    nan = np.asarray([0x7FF8_0000_0000_1234], dtype=np.uint64).view(np.float64)[0]
    array = np.asfortranarray(np.asarray([[1.5, -0.0], [np.inf, nan]], dtype=">f8"))
    value = {
        "none": None, "bool": True, "int": 17, "float": -0.0,
        "tuple": (np.int64(9), "x"), "list": [1.0, "1"], "array": array,
        "bytes": b"\x00\xff", "dtype": np.dtype("uint32"),
    }
    restored = decode_typed(encode_typed(value))
    assert type(restored["tuple"]) is tuple and type(restored["list"]) is list
    assert type(restored["tuple"][0]) is np.int64
    assert np.array_equal(restored["array"].view(np.uint64), array.view(np.uint64))
    assert restored["array"].dtype == array.dtype and restored["array"].flags.f_contiguous
    assert np.asarray([restored["float"]]).tobytes() == np.asarray([-0.0]).tobytes()
    assert restored["bytes"] == b"\x00\xff" and restored["dtype"] == np.dtype("uint32")
    with pytest.raises(CodecError, match="object-dtype"):
        encode_typed(np.asarray([object()], dtype=object))
    structured = np.dtype([("count", "<i4"), ("weight", "<f8")])
    with pytest.raises(CodecError, match="structured and subarray"):
        encode_typed(structured)
    with pytest.raises(CodecError, match="structured and subarray"):
        encode_typed(np.zeros(1, dtype=structured))
    with pytest.raises(CodecError, match="unsupported typed value"):
        encode_typed({1, 2})


def test_sqlite_journal_hash_chain_and_idempotency(tmp_path):
    journal = SQLiteJournal(tmp_path / "events.sqlite", "owner-uuid", "test")
    first = journal.append_event("evt-1", "TEST", {"value": 1})
    assert journal.append_event("evt-1", "TEST", {"value": 1}).event_hash == first.event_hash
    assert len(journal.events()) == 1
    with pytest.raises(JournalError, match="idempotency conflict"):
        journal.append_event("evt-1", "TEST", {"value": 2})
    journal.append_event("evt-2", "TEST", {"value": 2})
    assert [event.sequence for event in journal.events()] == [1, 2]
    assert SQLiteJournal.inspect(
        tmp_path / "events.sqlite", journal_uuid="owner-uuid", owner_kind="test",
    )[0] == "active"


def test_journal_detects_event_chain_and_immutable_record_digest_corruption(tmp_path):
    journal = SQLiteJournal(tmp_path / "corrupt.sqlite", "owner-uuid", "test")
    journal.commit_records((("record", "one", b"canonical bytes"),), ())
    journal.append_event("first", "TEST", {"x": 1})
    connection = sqlite3.connect(journal.path)
    try:
        connection.execute("UPDATE immutable_records SET digest=?", (_digest("bad"),))
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(JournalError, match="immutable record digest"):
        journal.immutable_records()

    event_journal = SQLiteJournal(tmp_path / "corrupt-event.sqlite", "event-owner", "test")
    event_journal.append_event("first", "TEST", {"x": 1})
    event_journal.append_event("second", "TEST", {"x": 2})
    connection = sqlite3.connect(event_journal.path)
    try:
        connection.execute("UPDATE events SET event_hash=? WHERE event_id='first'", (_digest("bad-event"),))
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(JournalError, match="event hash"):
        SQLiteJournal(event_journal.path, "event-owner", "test", create=False)
    with pytest.raises(JournalError, match="event hash"):
        event_journal.events()
    with pytest.raises(JournalError, match="unusable after an integrity failure"):
        event_journal.append_event("after-corruption", "TEST", {"x": 3})


def test_genesis_creates_ordered_identities_and_durable_g4(tmp_path):
    pair = _pair()
    coordinator, cells = _coordinator(tmp_path, pair)
    result = coordinator.reconcile(pair)
    assert result.stage == "G4" and result.readiness is not None
    assert result.readiness.cell_identity_ids == tuple(cell.identity_id for cell in cells)
    assert coordinator.require_ready(pair) == result.readiness
    for role, path, cell in zip(ARM_ROLES, (tmp_path / "lshade.sqlite", tmp_path / "de.sqlite"), cells):
        assert SQLiteJournal(path, cell.cell_journal_uuid, role, create=False).get_immutable_record(
            "cell_identity", cell.identity_id,
        ) == cell.canonical_bytes
    events = SQLiteJournal(tmp_path / "pair.sqlite", pair.pair_journal_uuid, "pair", create=False).events()
    assert [event.event_type for event in events] == [
        "PAIR_IDENTITY_COMMITTED", "GENESIS_ROSTER_COMMITTED", "ALL_IDENTITIES_READY",
    ]
    barrier = events[-1].payload
    assert barrier["schema"] == "stage5a2_all_identities_ready_v1" and barrier["ready"] is True
    assert barrier["pair_identity_sha256"] == pair.identity_sha256
    assert barrier["common_config_sha256"] == pair.config_sha256
    assert barrier["environment_sha256"] == pair.environment_sha256
    assert barrier["arm_config_hashes"] == [[role, value] for role, value in pair.arm_config_hashes]
    assert coordinator.reconcile(pair).readiness == result.readiness


@pytest.mark.parametrize("stop_after", ["G0", "G1", "G2", "G3", "G4"])
def test_genesis_crash_boundaries_reconcile_fail_closed(tmp_path, stop_after):
    pair = _pair()
    coordinator, _ = _coordinator(tmp_path, pair)

    class SimulatedCrash(RuntimeError):
        pass

    def hook(stage):
        if stage == stop_after:
            raise SimulatedCrash(stage)

    with pytest.raises(SimulatedCrash):
        coordinator.reconcile(pair, fault_hook=hook)
    result = coordinator.reconcile(pair)
    assert result.stage == "G4" and coordinator.require_ready(pair) == result.readiness


def test_genesis_rejects_orphan_conflict_and_post_g4_identity_loss(tmp_path):
    pair = _pair()
    coordinator, cells = _coordinator(tmp_path, pair)
    orphan = SQLiteJournal(tmp_path / "lshade.sqlite", cells[0].cell_journal_uuid, "lshade")
    assert orphan.is_pristine()
    with pytest.raises(GenesisError, match="orphan cell"):
        coordinator.reconcile(pair)

    pair = _pair()
    coordinator, cells = _coordinator(tmp_path / "conflict", pair)

    class SimulatedCrash(RuntimeError):
        pass

    with pytest.raises(SimulatedCrash):
        coordinator.reconcile(pair, fault_hook=lambda stage: (_ for _ in ()).throw(SimulatedCrash()) if stage == "G1" else None)
    cell_journal = SQLiteJournal(tmp_path / "conflict/lshade.sqlite", cells[0].cell_journal_uuid, "lshade")
    cell_journal.append_event("unexpected", "UNEXPECTED", {"x": 1})
    with pytest.raises(GenesisError, match="not pristine"):
        coordinator.reconcile(pair)

    pair = _pair()
    coordinator, _ = _coordinator(tmp_path / "lost", pair)
    coordinator.reconcile(pair)
    lost = tmp_path / "lost/de.sqlite"
    lost.unlink()
    with pytest.raises((GenesisError, JournalError)):
        coordinator.reconcile(pair)
    assert not lost.exists()


def test_pcg64_state_codec_restores_exact_state():
    generator = np.random.Generator(np.random.PCG64(4421))
    generator.integers(0, 100, size=3, dtype=np.uint32)
    encoded = pcg64_state(generator)
    clone = np.random.Generator(np.random.PCG64(1))
    restore_pcg64_state(clone, encoded)
    assert pcg64_state(clone) == encoded
    assert encode_typed(generator.random(5)) == encode_typed(clone.random(5))


def test_every_allowed_rng_method_replays_committed_results_without_draw(tmp_path):
    pair = _pair()
    cell = _cell_identity(pair, "controlled_de")
    journal = SQLiteJournal(tmp_path / "rng.sqlite", cell.cell_journal_uuid, "controlled_de")
    journal.commit_identity(cell)
    generator = np.random.Generator(np.random.PCG64(7931))
    service = RNGCallService(generator, journal)
    cases = (
        ("integers", (0, 100), {"dtype": np.dtype("uint32")}),
        ("choice", (np.asarray([2, 4, 8, 16]),), {"size": 2, "replace": False}),
        ("random", (), {"size": (2, 3)}), ("normal", (0.25, 0.75), {"size": 3}),
        ("standard_cauchy", (), {"size": 2}),
        ("uniform", (np.asarray([0.0, 1.0]), np.asarray([1.0, 2.0])), {}),
        ("permutation", (np.asarray([1, 3, 5, 7]),), {}),
    )
    identities = [RNGCallIdentity(cell.identity_id, "controlled_de", "step", (i,), i) for i in range(len(cases))]
    outputs, invocations = [], []
    invoke = service._invoke
    service._invoke = lambda method, args, kwargs: (invocations.append(method), invoke(method, args, kwargs))[1]
    for identity, (method, args, kwargs) in zip(identities, cases):
        outputs.append(service.call(identity, method, *args, **kwargs))
    final_state = pcg64_state(generator)
    assert invocations == [case[0] for case in cases]
    assert len([e for e in journal.events() if e.event_type == "RNG_DRAW_COMMITTED"]) == 7

    replay_generator = np.random.Generator(np.random.PCG64(7931))
    replay = RNGCallService(replay_generator, journal)
    replay._invoke = lambda *_: (_ for _ in ()).throw(AssertionError("committed RNG call redrawn"))
    replayed = [replay.call(identity, method, *args, **kwargs)
                for identity, (method, args, kwargs) in zip(identities, cases)]
    assert [encode_typed(value) for value in replayed] == [encode_typed(value) for value in outputs]
    assert pcg64_state(replay_generator) == final_state


def test_pending_rng_call_regenerates_from_prestate_and_request_mismatch_is_pre_draw(tmp_path):
    pair = _pair()
    cell = _cell_identity(pair, "lshade")
    journal = SQLiteJournal(tmp_path / "pending.sqlite", cell.cell_journal_uuid, "lshade")
    journal.commit_identity(cell)
    identity = RNGCallIdentity(cell.identity_id, "lshade", "generation-0", (0, "target", 0), 0)
    seed = 8871
    service = RNGCallService(np.random.Generator(np.random.PCG64(seed)), journal)
    invoke = service._invoke
    lost = None

    def crash_after_return(method, args, kwargs):
        nonlocal lost
        lost = invoke(method, args, kwargs)
        raise RuntimeError("simulated crash after PCG64 return")

    service._invoke = crash_after_return
    with pytest.raises(RuntimeError, match="simulated crash"):
        service.call(identity, "normal", 0.0, 1.0, size=4)
    assert lost is not None and [e.event_type for e in journal.events()] == [
        "CELL_IDENTITY_COMMITTED", "RNG_DRAW_STARTED",
    ]
    # Recovery resets even a fresh process with an arbitrary transient state
    # to the durable prestate before regenerating the pending logical call.
    progressed = np.random.Generator(np.random.PCG64(seed))
    progressed.random(11)
    recovered = RNGCallService(progressed, journal)
    output = recovered.call(identity, "normal", 0.0, 1.0, size=4)
    assert encode_typed(output) == encode_typed(lost)
    events = journal.events()
    start, commit = [event for event in events if event.event_type.startswith("RNG_DRAW_")]
    assert start.payload["schema"] == commit.payload["schema"] == "stage5a2_rng_call_v1"
    assert hashlib.sha256(encode_typed(start.payload["pre_state"])).hexdigest() == start.payload["pre_state_sha256"]
    assert hashlib.sha256(encode_typed(commit.payload["post_state"])).hexdigest() == commit.payload["post_state_sha256"]
    assert hashlib.sha256(commit.payload["result_typed"]).hexdigest() == commit.payload["result_sha256"]
    mismatch = RNGCallService(np.random.Generator(np.random.PCG64(seed)), journal)
    mismatch._invoke = lambda *_: (_ for _ in ()).throw(AssertionError("mismatch drew"))
    with pytest.raises(RNGProtocolError, match="mismatch"):
        mismatch.call(identity, "normal", 1.0, 1.0, size=4)


def test_invalid_rng_requests_and_ordinals_reject_before_any_start(tmp_path):
    pair = _pair()
    cell = _cell_identity(pair, "lshade")
    journal = SQLiteJournal(tmp_path / "invalid.sqlite", cell.cell_journal_uuid, "lshade")
    journal.commit_identity(cell)
    generator = np.random.Generator(np.random.PCG64(31))
    service = RNGCallService(generator, journal)
    before = pcg64_state(generator)
    identity = RNGCallIdentity(cell.identity_id, "lshade", "step", (), 0)
    with pytest.raises(RNGProtocolError, match="not permitted"):
        service.call(identity, "bytes", 3)
    with pytest.raises(RNGProtocolError, match="scale"):
        service.call(identity, "normal", 0.0, -1.0)
    invalid = (
        ("integers", (), {}),
        ("integers", (0, 0), {}),
        ("integers", (0, 300), {"dtype": np.dtype("uint8")}),
        ("random", (), {"dtype": np.dtype("float16")}),
        ("uniform", (np.asarray([0.0, 1.0]), np.asarray([1.0, 2.0])), {"size": (3,)}),
        ("choice", (3,), {"size": 4, "replace": False}),
        ("choice", (3,), {"p": [0.25, 0.25]}),
        ("permutation", (np.arange(3),), {"axis": 1}),
        ("standard_cauchy", (), {"size": -1}),
    )
    for method, args, kwargs in invalid:
        with pytest.raises(RNGProtocolError):
            service.call(identity, method, *args, **kwargs)
    assert [event for event in journal.events() if event.event_type.startswith("RNG_DRAW_")] == []
    assert pcg64_state(generator) == before
    skipped = RNGCallIdentity(cell.identity_id, "lshade", "step", (), 1)
    with pytest.raises(RNGProtocolError, match="ordinal"):
        service.call(skipped, "random")
    assert [event for event in journal.events() if event.event_type.startswith("RNG_DRAW_")] == []


def test_sampler_requires_g4_before_any_rng_or_geometry_call(tmp_path):
    metadata = _metadata("P_D")
    pair = _pair(metadata)
    journal = SQLiteJournal(tmp_path / "sampler.sqlite", pair.pair_journal_uuid, "pair")
    genesis = GenesisCoordinator(
        tmp_path / "sampler.sqlite", (tmp_path / "sampler-lshade.sqlite", tmp_path / "sampler-de.sqlite"),
    )

    class CounterRNG:
        def __init__(self):
            self.calls = 0
            self.journal = journal

        def call(self, *_args, **_kwargs):
            self.calls += 1
            return np.asarray([0.25, 0.5])

    rng, geometry_calls = CounterRNG(), []
    with pytest.raises(InitializationGateError, match="before verified durable G4"):
        sample_initial_population(
            metadata=metadata, pair_identity=pair, genesis=genesis, rng=rng,
            normalize=_normalize(metadata), physical=_physical(metadata),
            geometry_valid=lambda _: geometry_calls.append(True) or True,
        )
    assert rng.calls == 0 and geometry_calls == []
    generator = np.random.Generator(np.random.PCG64(_seed(pair)))
    service = RNGCallService(generator, journal, genesis=genesis, pair_identity=pair)
    state_before = pcg64_state(generator)
    with pytest.raises(RNGProtocolError, match="before verified durable G4"):
        service.call(
            RNGCallIdentity(pair.identity_id, "common_sampler", "sampler-draw-0", (0,), 0),
            "uniform", np.zeros(metadata.dimension), np.ones(metadata.dimension),
        )
    assert journal.events() == () and pcg64_state(generator) == state_before


def test_population_seal_preflights_attachments_and_no_evaluator_before_both_certs(tmp_path):
    metadata = _metadata("P_D")
    pair = _pair(metadata)
    coordinator, cells = _coordinator(tmp_path, pair)
    coordinator.reconcile(pair)
    pair_journal = SQLiteJournal(tmp_path / "pair.sqlite", pair.pair_journal_uuid, "pair", create=False)
    journals = tuple(
        SQLiteJournal(path, cell.cell_journal_uuid, role, create=False)
        for path, cell, role in zip((tmp_path / "lshade.sqlite", tmp_path / "de.sqlite"), cells, ARM_ROLES)
    )
    vectors = [[0.1, 0.125], [0.1, 0.125], [0.2, 0.25]]
    vectors.extend([[i / 512.0, (i + 1) / 1024.0] for i in range(1, POPULATION_SIZE + 1)])
    scripted = _ScriptedRNG(vectors, pair_journal, _seed(pair))
    geometry_inputs = []

    def geometry(vector):
        geometry_inputs.append(vector.copy())
        return not np.array_equal(vector, [0.2, 0.25])

    seal = sample_initial_population(
        metadata=metadata, pair_identity=pair, genesis=coordinator, rng=scripted,
        normalize=_normalize(metadata), physical=_physical(metadata), geometry_valid=geometry,
    )
    assert len(seal.members) == POPULATION_SIZE and seal.draws == POPULATION_SIZE + 2
    assert seal.duplicate_rejections == seal.geometry_rejections == 1
    assert len(geometry_inputs) == 235
    draws = [e for e in pair_journal.events() if e.event_type == "SAMPLER_DRAW"]
    assert [e.payload["classification"] for e in draws[:3]] == ["accepted", "duplicate_reject", "geometry_reject"]
    for cell, journal in zip(cells, journals):
        before = journal.get_immutable_record("cell_identity", cell.identity_id)
        attachment = attach_population(cell=cell, journal=journal, pair_journal=pair_journal, seal=seal)
        assert journal.get_immutable_record("cell_identity", cell.identity_id) == before == cell.canonical_bytes
        payload = journal.get_event(
            f"POPULATION_ATTACHMENT_ATTACHED:{cell.identity_id}:{seal.population_sha256}:{seal.representation_sha256}"
        )["payload"]
        assert payload["pair_identity_id"] == pair.identity_id
        assert attachment.population_sha256 == seal.population_sha256
        assert attachment.representation_sha256 == seal.representation_sha256

    lshade = preflight_lshade(seal, cells[0], physical=_physical(metadata), canonicalize=_canonicalizer(metadata))
    controlled = preflight_controlled_de(
        seal, cells[1], canonicalize=_canonicalizer(metadata), normalize=_normalize(metadata),
    )
    calls = []
    with pytest.raises(InitializationGateError, match="both durable"):
        require_both_preflight_certificates(
            seal=seal, pair_identity_id=pair.identity_id, cells=cells, journals=journals,
        )
    with pytest.raises(InitializationGateError, match="both preflight"):
        dispatch_initial_evaluation(
            None, role="lshade", seal=seal, member=seal.members[0], cells=cells, journals=journals,
            evaluator=lambda x: calls.append(x),
        )
    assert calls == []
    token = persist_both_preflight_certificates(
        seal=seal, pair_identity_id=pair.identity_id, cells=cells, journals=journals,
        lshade_certificate=lshade, controlled_de_certificate=controlled,
    )
    forged_token = replace(token, controlled_de_certificate_sha256=_digest("forged-ready"))
    with pytest.raises(InitializationGateError, match="differs from the durable"):
        dispatch_initial_evaluation(
            forged_token, role="lshade", seal=seal, member=seal.members[0], cells=cells, journals=journals,
            evaluator=lambda x: calls.append(x),
        )
    assert calls == []
    result = dispatch_initial_evaluation(
        token, role="lshade", seal=seal, member=seal.members[0], cells=cells, journals=journals,
        evaluator=lambda x: calls.append(x.copy()) or "synthetic",
    )
    assert result == "synthetic" and len(calls) == 1
    assert calls[0].tobytes() == seal.members[0].sealed_physical_le_f64


def test_preflight_vector_or_key_mismatch_blocks_both_arms(tmp_path):
    metadata = _metadata("P_D")
    pair = _pair(metadata)
    coordinator, cells = _coordinator(tmp_path, pair)
    coordinator.reconcile(pair)
    pair_journal = SQLiteJournal(tmp_path / "pair.sqlite", pair.pair_journal_uuid, "pair", create=False)
    scripted = _ScriptedRNG(
        [[i / 512.0, (i + 1) / 1024.0] for i in range(1, POPULATION_SIZE + 1)],
        pair_journal, _seed(pair),
    )
    seal = sample_initial_population(
        metadata=metadata, pair_identity=pair, genesis=coordinator, rng=scripted,
        normalize=_normalize(metadata), physical=_physical(metadata), geometry_valid=lambda _: True,
    )
    journals = tuple(
        SQLiteJournal(path, cell.cell_journal_uuid, role, create=False)
        for path, cell, role in zip((tmp_path / "lshade.sqlite", tmp_path / "de.sqlite"), cells, ARM_ROLES)
    )
    for cell, journal in zip(cells, journals):
        attach_population(cell=cell, journal=journal, pair_journal=pair_journal, seal=seal)
    good = preflight_lshade(seal, cells[0], physical=_physical(metadata), canonicalize=_canonicalizer(metadata))

    def changed(values):
        vector, _ = _canonicalizer(metadata)(values)
        vector = vector.copy()
        vector[0] = np.nextafter(vector[0], np.inf)
        return vector, tuple(vector)

    with pytest.raises(InitializationError, match="preflight mismatch"):
        preflight_controlled_de(seal, cells[1], canonicalize=changed, normalize=_normalize(metadata))
    assert not [e for journal in journals for e in journal.events()
                if e.event_type == "INITIALIZATION_PREFLIGHT_CERTIFICATE"]
    assert good.population_sha256 == seal.population_sha256


def test_preflight_certificate_forgery_and_wrong_pair_fail_closed(tmp_path):
    metadata = _metadata("P_D")
    pair = _pair(metadata)
    coordinator, cells = _coordinator(tmp_path, pair)
    coordinator.reconcile(pair)
    pair_journal = SQLiteJournal(tmp_path / "pair.sqlite", pair.pair_journal_uuid, "pair", create=False)
    scripted = _ScriptedRNG(
        [[i / 512.0, (i + 1) / 1024.0] for i in range(1, POPULATION_SIZE + 1)],
        pair_journal, _seed(pair),
    )
    seal = sample_initial_population(
        metadata=metadata, pair_identity=pair, genesis=coordinator, rng=scripted,
        normalize=_normalize(metadata), physical=_physical(metadata), geometry_valid=lambda _: True,
    )
    journals = tuple(
        SQLiteJournal(path, cell.cell_journal_uuid, role, create=False)
        for path, cell, role in zip((tmp_path / "lshade.sqlite", tmp_path / "de.sqlite"), cells, ARM_ROLES)
    )
    for cell, journal in zip(cells, journals):
        attach_population(cell=cell, journal=journal, pair_journal=pair_journal, seal=seal)
    left = preflight_lshade(seal, cells[0], physical=_physical(metadata), canonicalize=_canonicalizer(metadata))
    right = preflight_controlled_de(seal, cells[1], canonicalize=_canonicalizer(metadata), normalize=_normalize(metadata))
    forged = replace(right, ordered_vector_key_sha256=_digest("forged"))
    with pytest.raises(InitializationError, match="sealed population"):
        persist_both_preflight_certificates(
            seal=seal, pair_identity_id=pair.identity_id, cells=cells, journals=journals,
            lshade_certificate=left, controlled_de_certificate=forged,
        )
    with pytest.raises(InitializationError, match="different pair"):
        persist_both_preflight_certificates(
            seal=seal, pair_identity_id=_digest("other"), cells=cells, journals=journals,
            lshade_certificate=left, controlled_de_certificate=right,
        )


def test_sampler_cap_records_exact_shortfall_without_search_evaluation(tmp_path):
    metadata = _metadata("P_D")
    pair = _pair(metadata)
    coordinator = _coordinator(tmp_path, pair)[0]
    coordinator.reconcile(pair)
    journal = _MemoryJournal(pair.pair_journal_uuid)
    scripted = _ScriptedRNG([[0.25, 0.5]] * 10_000, journal, _seed(pair))
    geometry_calls = 0

    def geometry(_vector):
        nonlocal geometry_calls
        geometry_calls += 1
        return False

    with pytest.raises(InitializationError, match="exhausted 10000 draws with 0 accepted"):
        sample_initial_population(
            metadata=metadata, pair_identity=pair, genesis=coordinator, rng=scripted,
            normalize=_normalize(metadata), physical=_physical(metadata), geometry_valid=geometry,
        )
    failure = journal._events[f"INITIALIZATION_FAILED:{pair.identity_id}:10000"][1]
    assert failure == {
        "pair_identity_id": pair.identity_id, "status": "INITIALIZATION_FAILED",
        "draws": 10_000, "accepted": 0, "duplicate_rejections": 0,
        "geometry_rejections": 10_000, "max_draws": 10_000,
    }
    assert len(scripted.calls) == geometry_calls == 10_000
    assert not any(kind in {"INITIALIZATION_MEMBER_COMMITTED", "EVALUATION_RESULT_COMMITTED"}
                   for kind, _ in journal._events.values())


def test_sampler_resume_replays_committed_calls_without_redraw_and_rebuilds_seal(tmp_path):
    metadata = _metadata("P_D")
    pair = _pair(metadata)
    coordinator, _cells = _coordinator(tmp_path, pair)
    coordinator.reconcile(pair)
    journal = SQLiteJournal(tmp_path / "pair.sqlite", pair.pair_journal_uuid, "pair", create=False)
    seed = _seed(pair)
    first = RNGCallService(
        np.random.Generator(np.random.PCG64(seed)), journal, genesis=coordinator, pair_identity=pair,
    )

    class SimulatedCrash(RuntimeError):
        pass

    def stop_after_three(index):
        if index == 2:
            raise SimulatedCrash("sampler draw committed")

    with pytest.raises(SimulatedCrash):
        sample_initial_population(
            metadata=metadata, pair_identity=pair, genesis=coordinator, rng=first,
            normalize=_normalize(metadata), physical=_physical(metadata), geometry_valid=lambda _: True,
            after_draw_commit=stop_after_three,
        )
    assert len([e for e in journal.events() if e.event_type == "SAMPLER_DRAW"]) == 3

    generator = np.random.Generator(np.random.PCG64(seed))
    replay = RNGCallService(generator, journal, genesis=coordinator, pair_identity=pair)
    invoked = []
    invoke = replay._invoke
    replay._invoke = lambda method, args, kwargs: (invoked.append(method), invoke(method, args, kwargs))[1]
    seal = sample_initial_population(
        metadata=metadata, pair_identity=pair, genesis=coordinator, rng=replay,
        normalize=_normalize(metadata), physical=_physical(metadata), geometry_valid=lambda _: True,
    )
    assert len(seal.members) == POPULATION_SIZE and seal.draws == POPULATION_SIZE
    assert invoked == ["uniform"] * (POPULATION_SIZE - 3)
    assert len([e for e in journal.events() if e.event_type == "SAMPLER_DRAW"]) == POPULATION_SIZE
    assert len([e for e in journal.events() if e.event_type == "RNG_DRAW_COMMITTED"]) == POPULATION_SIZE
