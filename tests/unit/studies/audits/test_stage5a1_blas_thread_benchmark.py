import csv
import json

import pytest

from sawopt.studies.audits.stage5a1_blas_thread_benchmark import (
    BLAS_SETTINGS,
    build_child_environment,
    shuffled_single_order,
    summarize_single_profiles,
    summarize_throughput,
    shuffled_parallel_order,
    validate_blas_pools,
    validate_parallel_job_results,
    validate_profile_summary,
    write_benchmark_outputs,
)


THREAD_VARIABLES = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
)
PROFILE_STAGES = ("B_s", "C_s", "D_s", "E_s", "F_s", "G_stage4a_call_s")
CELL_IDENTITIES = tuple(
    (topology, seed)
    for topology in ("P_D", "D_P")
    for seed in (20261007, 20261009, 20261011)
)
GRID_IDENTITIES = {
    "search": "212dd2b0b71ddeffb7a8865937d132ee596870f25c989ac7d90c5dab6fd7faa0",
    "common": "2e24c4ce3f96c38baba44dc83bc60f95954a6b677cb2a37d63078e78c4cea42f",
}


def _pool(name="libopenblas.so", threads=1):
    return {
        "user_api": "blas", "internal_api": "openblas", "prefix": "libopenblas",
        "filepath": name, "version": "0.3.test", "num_threads": threads,
    }


def _profile_summary(setting):
    configured = BLAS_SETTINGS[setting]
    child_env = build_child_environment(setting, {})
    pools = [_pool("numpy-openblas", int(configured or 3)),
             _pool("scipy-openblas", int(configured or 3))]
    summaries = []
    for topology, seed in CELL_IDENTITIES:
        for grid in ("search", "common"):
            for index, stage in enumerate(PROFILE_STAGES):
                median = 0.08 + index * 0.01
                summaries.append({
                    "topology": topology, "seed": seed, "grid": grid,
                    "stage": stage, "n": 7, "median_s": median,
                    "min_s": median * 0.9, "max_s": median * 1.1,
                    "mad_s": median * 0.02,
                })
    thread_environment = {name: child_env.get(name) for name in THREAD_VARIABLES}
    return {
        "status": "COMPLETE", "benchmark_tree_dirty": False,
        "benchmark_commit_sha": "abc123", "benchmark_utility_sha256": "hash",
        "sample_count": 84, "timed_repetitions_per_condition": 7,
        "warmups_per_condition_and_method": 2,
        "candidate_input_files": {f"{topology}/{seed}": "hash"
                                   for topology, seed in CELL_IDENTITIES},
        "grid_identities": {
            "search": {"frequency_count": 1001, "sha256": GRID_IDENTITIES["search"]},
            "common": {"frequency_count": 9113, "grid_id": GRID_IDENTITIES["common"]},
        },
        "parity_results": [{"status": "PASS"} for _ in range(12)],
        "summaries": summaries,
        "environment": {
            "threadpools": pools, "thread_environment": thread_environment,
            "affinity_cpu_count": 16, "process_thread_count": 4,
        },
    }


def test_child_environment_applies_setting_before_import_and_clears_default():
    inherited = {"OPENBLAS_NUM_THREADS": "8", "OMP_NUM_THREADS": "3", "PATH": "/bin"}

    assert build_child_environment("quad", inherited)["OPENBLAS_NUM_THREADS"] == "4"
    assert build_child_environment("default", inherited) == {
        "OMP_NUM_THREADS": "3", "PATH": "/bin",
    }
    with pytest.raises(ValueError, match="unknown BLAS setting"):
        build_child_environment("eight", inherited)


@pytest.mark.parametrize("setting,threads", [("single", 1), ("dual", 2), ("quad", 4)])
def test_blas_pool_validation_requires_each_loaded_library_to_match(setting, threads):
    env = build_child_environment(setting, {"OMP_NUM_THREADS": "2"})
    evidence = validate_blas_pools(
        setting, env, [_pool("numpy-openblas", threads), _pool("scipy-openblas", threads)],
    )

    assert evidence["valid"] is True
    assert evidence["effective_blas_threads"] == [threads, threads]
    assert evidence["potential_conflicts"] == {"OMP_NUM_THREADS": "2"}
    with pytest.raises(ValueError, match="does not match requested"):
        validate_blas_pools(setting, env, [_pool("numpy-openblas", threads), _pool("scipy-openblas", threads + 1)])


def test_default_pool_validation_requires_unset_variable_and_reports_all_pools():
    env = build_child_environment("default", {"OPENBLAS_NUM_THREADS": "9"})
    evidence = validate_blas_pools(
        "default", env, [_pool("numpy-openblas", 64), _pool("scipy-openblas", 64)],
    )

    assert evidence["valid"] is True
    assert evidence["effective_blas_threads"] == [64, 64]
    with pytest.raises(ValueError, match="OPENBLAS_NUM_THREADS must be unset"):
        validate_blas_pools("default", {**env, "OPENBLAS_NUM_THREADS": "9"}, [_pool(threads=64)])
    with pytest.raises(ValueError, match="no active BLAS pools"):
        validate_blas_pools("single", build_child_environment("single", {}), [])


def test_setting_order_is_reproducible_and_covers_all_settings():
    first = shuffled_single_order(20261009)

    assert first == shuffled_single_order(20261009)
    assert set(first) == set(BLAS_SETTINGS)


def test_profile_summary_rejects_invalid_runtime_or_incomplete_numerical_evidence():
    summary = _profile_summary("dual")

    assert validate_profile_summary("dual", summary)["valid"] is True
    summary["environment"]["threadpools"][1]["num_threads"] = 4
    with pytest.raises(ValueError, match="does not match requested"):
        validate_profile_summary("dual", summary)

    incomplete = _profile_summary("single")
    incomplete["parity_results"].pop()
    with pytest.raises(ValueError, match="parity results"):
        validate_profile_summary("single", incomplete)
    incomplete = _profile_summary("single")
    incomplete["summaries"] = [row for row in incomplete["summaries"]
                               if not (row["stage"] == "B_s" and row["grid"] == "search")]
    with pytest.raises(ValueError, match="B_s summary is incomplete"):
        validate_profile_summary("single", incomplete)


def test_single_profile_aggregation_uses_candidate_medians_and_default_speedup():
    profiles = {setting: _profile_summary(setting) for setting in BLAS_SETTINGS}

    result = summarize_single_profiles(profiles)

    row = next(row for row in result if row["setting"] == "single"
               and row["grid"] == "search" and row["stage"] == "B_s")
    assert row["candidate_count"] == 6
    assert row["samples_per_candidate"] == 7
    assert row["speedup_vs_default"] == pytest.approx(1.0)
    assert next(row for row in result if row["setting"] == "default"
                and row["grid"] == "search" and row["stage"] == "B_s")["speedup_vs_default"] == 1.0


def _throughput_rows():
    rows = []
    for setting in BLAS_SETTINGS:
        for workers in (1, 2, 4):
            for repetition in (1, 2):
                rows.append({
                    "setting": setting, "workers": workers, "repetition": repetition,
                    "job_count": 96, "evaluation_window_wall_s": 96 / (10 * workers),
                    "total_batch_wall_s": 1 + 96 / (10 * workers),
                    "setup_wall_s": 0.5, "worker_cpu_time_s": 9.0 * workers,
                    "affinity_cpu_count": 16, "peak_aggregate_rss_kib": 100000 * workers,
                    "peak_total_process_threads": workers * 4,
                })
    return rows


def test_throughput_summary_compares_worker_speedup_and_marks_missing_conditions():
    rows = _throughput_rows()
    summary = summarize_throughput(rows, repetitions_per_condition=2)
    four_workers = next(row for row in summary["conditions"]
                        if row["setting"] == "single" and row["workers"] == 4)

    assert summary["status"] == "COMPLETE"
    assert four_workers["median_jobs_per_second"] == pytest.approx(40.0)
    assert four_workers["speedup_vs_one_worker"] == pytest.approx(4.0)
    partial = summarize_throughput(rows[:-1], repetitions_per_condition=2)
    assert partial["status"] == "PARTIAL"
    assert {"setting": "default", "workers": 4, "repetition": 2} in partial["missing_runs"]
    incomplete_batch = [*rows]
    incomplete_batch[0] = {**incomplete_batch[0], "job_count": 95}
    with pytest.raises(ValueError, match="incomplete job count"):
        summarize_throughput(incomplete_batch, repetitions_per_condition=2)


def test_parallel_condition_order_is_seeded_and_covers_every_worker_setting_pair():
    first = shuffled_parallel_order(41, 2)

    assert first == shuffled_parallel_order(41, 2)
    assert len(first) == 2 * len(BLAS_SETTINGS) * 3
    assert {(row["setting"], row["workers"]) for row in first} == {
        (setting, workers) for setting in BLAS_SETTINGS for workers in (1, 2, 4)
    }
    assert [row["run_order"] for row in first] == list(range(1, len(first) + 1))


def test_parallel_job_results_check_all_candidates_and_existing_tolerance():
    jobs = [{
        "candidate": f"{topology}/{seed}", "objective": 1.0,
        "max_violation": 0.0, "sum_violation": 0.0, "feasible": True,
    } for topology, seed in CELL_IDENTITIES]
    repeated = [{**job, "objective": job["objective"] + 1e-14} for job in jobs]

    assert validate_parallel_job_results(
        [{"jobs": jobs}, {"jobs": repeated}], rtol=1e-10, atol=1e-12,
    ) == pytest.approx(1e-14)
    mismatch = [{**job, "objective": 1.01} if i == 0 else job
                for i, job in enumerate(jobs)]
    with pytest.raises(ValueError, match="objective mismatch"):
        validate_parallel_job_results([{"jobs": jobs}, {"jobs": mismatch}], rtol=1e-10, atol=1e-12)
    with pytest.raises(ValueError, match="cover all six"):
        validate_parallel_job_results([{"jobs": jobs[:2]}], rtol=1e-10, atol=1e-12)


def test_write_outputs_preserves_rows_and_refuses_existing_directory(tmp_path):
    output = tmp_path / "benchmark"
    single = [{"setting": "single", "grid": "search", "stage": "B_s", "median_s": 0.1}]
    throughput = [{"setting": "single", "workers": 1, "jobs_per_second": 10.0}]
    summary = {
        "status": "COMPLETE", "configurations": 4,
        "single_process_summary": single,
    }

    paths = write_benchmark_outputs(output, single, throughput, summary)

    with paths[0].open(newline="", encoding="utf-8") as stream:
        assert list(csv.DictReader(stream))[0]["median_s"] == "0.1"
    assert json.loads(paths[2].read_text(encoding="utf-8")) == summary
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_benchmark_outputs(output, single, throughput, summary)
