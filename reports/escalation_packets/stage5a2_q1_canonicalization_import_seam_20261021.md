# Stage 5A-2 Q1 physics-free canonicalization import seam — Sol judgment packet

**Request:** bounded architecture/interface judgment before Q1 authorization or implementation.

**Current PR:** Draft [PR #51](https://github.com/MasayaTakagi/saw-com-optimizer/pull/51), review comment [#6314079583](https://github.com/MasayaTakagi/saw-com-optimizer/pull/51#issuecomment-6314079583).

**Reviewed base:** `main` / PR #50 merge `9427b404d302932b27f50d31919bb3fb95fcfcd4`; PR #51 reviewed head `82af8df376fd4e43de4f81659a15ee6a8bfc5555`.

**Scope:** design judgment only. No source edit, test, synthetic run, COM/network/physics call, optimizer execution, Stage 4C change, Q1 authorization or production launch is requested or permitted by this packet.

## 1. Decision requiring judgment

The independent PR #51 review found a concrete conflict in the planned Q1 no-COM import boundary: the Q1 synthetic path was told to reuse `HybridDesignSpace.canonicalize`, but importing its current module transitively imports COM/network code. The reviewer requires a physics-free seam that preserves the exact existing canonicalization output, avoids duplicate rounding logic or test-only import bypasses, and states any shared-source change and Stage 4C parity gate. This is a shared-source/module-interface design change, which the project Sol escalation policy classifies as high risk.

Please judge the proposed seam and its proof conditions below. Do not implement it or authorize Q1. If it is insufficient, give a bounded alternative or identify the blocking unknown; do not select a different rounding/canonicalization contract.

## 2. Read-only import-graph evidence

Relevant current source:

- `src/sawopt/problem/__init__.py` eagerly imports `.evaluator` and `.validation`.
- `src/sawopt/problem/evaluator.py` imports `..core.com`, `..core.network`, `..core.metrics`, and `..core.models`.
- `src/sawopt/problem/hybrid.py` imports `..core.hybrid`, `..core.metrics`, and `.dms_topologies`.
- `src/sawopt/core/hybrid.py` imports `.com`, `.network`, and `.metrics`.
- `src/sawopt/problem/dms_topologies.py` imports `..core.topology`; `src/sawopt/core/topology.py` imports `.com`.
- `src/sawopt/problem/hybrid.py::HybridDesignSpace.canonicalize` is currently a pure method but cannot be imported through its module path without triggering the package/module import graph above.
- `src/sawopt/__init__.py` and `src/sawopt/core/__init__.py` contain only docstrings; they do not themselves import model code. `src/sawopt/optimization/__init__.py` also contains only a docstring.

Current `HybridDesignSpace.canonicalize` behavior is:

1. `values = np.asarray(vector, dtype=float)`;
2. require shape `(self.dimension,)` and all finite;
3. `canonical = np.clip(values.copy(), self.bounds[:, 0], self.bounds[:, 1])`;
4. for the ordered integer indices, assign `np.floor(canonical[index] + 0.5)`;
5. clip again to the same lower/upper arrays;
6. construct `tuple(float(value) for value in canonical)` and return the NumPy array/key.

Exact NumPy operation order, dtype conversion, clipping, half-up integer rule, second clip, float-key construction, and IEEE-754 results are part of the frozen Q0 contract.

## 3. Candidate seam and planned source boundary (not approved/implemented)

Proposed Q1-A architecture, subject to this judgment:

1. Add a small dependency-leaf package/module such as `src/sawopt/design/canonicalization.py`. It may import NumPy and standard-library typing only; it must not import `sawopt.problem`, `core.com`, `core.network`, COM providers, topology evaluators, or production orchestration.
2. Move—not copy—the exact canonicalization implementation above into one pure function in that leaf, parameterized by the exact bounds, ordered integer-index tuple, dimension and topology label needed for validation/error reporting. Preserve statement order and NumPy expressions exactly. Do not add tolerance, casts beyond the current conversion, clipping, rounding, signed-zero policy or default behavior.
3. Change `HybridDesignSpace.canonicalize` into a thin delegate to this shared function. Its public method signature and returned array/key remain unchanged. Stage 4B/4C code continues to use `HybridDesignSpace`; Q1 imports only the new leaf and supplies its frozen design-space metadata, never importing `sawopt.problem.hybrid` or `sawopt.problem`.
4. Keep other existing `HybridDesignSpace` methods and physics-related code in their current module; this proposal is only to factor the pure canonicalization primitive, not move a solver, design decoder, geometry evaluator, COM model, comparator, or study runner.
5. Q1's integration/import-isolation check runs in a fresh process and asserts the Q1 runtime never imports or calls COM/provider/network modules. A separately scoped canonicalization compatibility check may import the old public `HybridDesignSpace` path solely to exercise `canonicalize`, with no evaluator/geometry/physics function call; alternatively use a fixed bit-exact golden corpus captured from that pre-refactor method. Do not use custom `importlib` loading, monkeypatch package initializers, `sys.modules` tricks, or a test-only module-loading bypass.

This refactor changes a shared module interface/source location, even though it is intended to preserve numerical behavior. Q1-A must report it explicitly and cannot merge it as an invisible test utility.

## 4. Proposed preservation evidence

Before moving the method, create a bounded deterministic characterization corpus through the existing public method, without calling physics. Cover at least: all supported topologies/dimensions, finite/infinite/NaN input rejection, wrong shape, active lower/upper clipping, integer half-up boundaries below/at/above ties, bounds that clip rounded integer values, continuous coordinates, signed zero, adjacent representable binary64 values, returned key type/order, and exact binary64 bytes. Store expected bytes/keys with source SHA, NumPy version and fixture generator provenance.

After extraction, require:

- old public `HybridDesignSpace.canonicalize` path and new leaf produce identical returned vector bytes, key values and exception class/message for the full corpus;
- static review confirms one production implementation (the shared leaf), not two manually synchronized rounding algorithms;
- focused tests call the pure leaf in a fresh process and verify no COM/provider/network module is imported;
- Stage 4A/Stage 4B/Stage 4C canonicalization/initialization and protected saved-record/checkpoint semantics have an explicit parity review. No Stage 4C run is authorized or needed; use bounded no-physics canonicalization fixtures and existing non-production regression tests only after separate Q1 implementation permission. Preserve Stage 4C data/checkpoints byte-for-byte and do not modify its evaluator, optimizer rules or state schema;
- an independent review of the shared-source refactor accepts the exact behavior-preservation evidence before Q1-A readiness is granted.

The corpus and source diff are verification evidence, not permission to run the Q0 optimizer comparison. If a later test plan needs physical COM/network evaluation to establish parity, stop; that is outside Q1 and needs its own experiment decision.

## 5. Questions for bounded judgment

1. Is the single-source, dependency-leaf extraction plus unchanged `HybridDesignSpace` delegation an acceptable physics-free Q1 import seam, given the observed package import chain?
2. Are the proposed bit-exact pre/post characterization fixtures, no-COM leaf-isolation check, source-level operation-order review and Stage 4C protection review sufficient to bound this shared-source refactor, or is a different preservation proof necessary?
3. May the *integration runtime* be required to have no COM/provider/network imports while the separately scoped public-method compatibility characterization imports the legacy module path but never executes physics? If not, which test structure preserves both independent old-behavior comparison and the strict import boundary without a test-only loader or duplicate production logic?
4. What exact preconditions should Q1-A satisfy before this interface refactor is considered ready for independent GitHub review?

Return exactly:

- `DECISION`: `APPROVE_CANDIDATE_SEAM` / `REQUEST_REVISIONS` / `BLOCK`
- `IMPORT_GRAPH_ASSESSMENT`
- `CANONICALIZATION_SEAM_ASSESSMENT`
- `PARITY_AND_STAGE4C_PROTECTION_REQUIREMENTS`
- `Q1_IMPORT_BOUNDARY`
- `REMAINING_RISKS`
- `AUTHORIZATION_BOUNDARY`

## 6. Routing and authorization boundary

Requested routing: one read-only judgment agent, `model="openai/gpt-6.1-sol"`, Pi `thinking="medium"`, tool allowlist `read`, non-persistent. Inspect the actual child-session provider/model/thinking metadata after completion; requested routing is not observed identity. Do not fall back to another model/provider.

The requested judgment is limited to the architecture seam and evidence criteria. It grants no implementation, file-change, Git/GitHub, test, synthetic execution, COM/network/physics, optimizer, Q0 revision, Q1 start, or production permission. Q1 remains `PLANNED / IMPLEMENTATION NOT STARTED / AWAITING SEPARATE USER AUTHORIZATION`. Any implementation still needs that separate user authorization, followed by the applicable implementation and independent GitHub review gates.

## 7. Sol judgment and routing record

**Decision:** `APPROVE_CANDIDATE_SEAM`, conditional on the exact operation order/metadata/output invariants and the full preservation package in §§3–4. This is approval of the design candidate only, not implementation correctness or Q1 readiness. Sol confirmed the import-path conflict and accepted the single dependency-leaf extraction with same-signature `HybridDesignSpace` delegation as suitably narrow. Do not refactor decoder rounding or adjacent physics/design code. Require independent pre-extraction fixtures, exact byte/key/error comparisons, metadata and caller parity, fresh-process leaf import isolation, and explicit Stage 4A/4B/4C protection evidence.

**Import-scope clarification:** the synthetic integration runtime must remain no-COM/provider/network import/call. A separately scoped legacy compatibility characterization can import the existing public path only to call `canonicalize`, with no decode, geometry, provider, evaluator, network or physics call. This exception must be explicitly scoped in the user's separate Q1-A authorization before execution; this Sol judgment does not waive Q0-R3 prohibitions. If unauthorized and no already-authorized baseline corpus exists, Q1-A must stop rather than bypass imports or duplicate production logic.

**Observed child-session routing metadata:** requested `openai/gpt-6.1-sol`, Pi `thinking=medium`, `tools=["read"]`, non-persistent. The inspected record `/home/user/.pi/agent/subagent-sessions/2026-10-21T11-03-12-650Z_01a15e21-2409-7106-9a2c-fcdf647f8b6d.jsonl` (session ID `01a15e21-2409-7106-9a2c-fcdf647f8b6d`) records provider `openai`, API `openai-responses`, model `gpt-6.1-sol`, `thinkingLevel=medium`, the review response, and normal completion (`stopReason=stop`, `rawStopReason=completed`). The runtime setting is not proof of internal reasoning effort. Sol noted that the GitHub comment was assessed through the supplied packet rather than retrieved independently in the child review.

No source implementation, test, characterization, synthetic execution, COM/physics call, Stage 4C change, or Q1 authorization resulted from this judgment.
