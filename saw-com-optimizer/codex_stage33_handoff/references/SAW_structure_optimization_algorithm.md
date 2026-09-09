# SAW構造最適化アルゴリズム 改良案

## 1. 目的

本プロジェクトでは、SAWフィルタの入出力インピーダンスを変化させた各条件に対して、
SAW構造そのものを再最適化し、最終的にどのポートインピーダンスで最も良い特性が得られるかを評価する。

本書では、そのうち **SAW構造側の探索アルゴリズム** に絞り、
現在の Differential Evolution（DE）中心の構成をより効率的・高精度にするための改良案をまとめる。

---

## 2. 現行方式の想定

現状は概ね以下の構成を想定する。

```text
Topology / wiring を選択
        ↓
Differential Evolution
  - 連続変数
  - 整数変数
        ↓
coarse frequency grid で評価
        ↓
dense frequency grid で再評価
        ↓
必要に応じて再最適化
```

この方式は実装しやすく堅牢だが、SAW構造最適化に対しては以下の改善余地がある。

---

## 3. 現行DEの課題

### 3.1 探索パラメータが固定的

標準DEでは、たとえば以下のようなパラメータを事前に固定する。

```python
mutation = 0.7
recombination = 0.9
```

しかし実際には、

- 探索初期：大きく動いて広い領域を探索したい
- 探索終盤：良い解の近傍を細かく探索したい

という違いがある。

固定パラメータでは、この両方を最適に満たすことが難しい。

---

### 3.2 全変数を同じように扱ってしまう

SAW設計変数には性質の異なる変数が混在する。

例：

- period
- aperture
- gap
- finger pairs
- reflector pairs
- center側パラメータ
- outer側パラメータ
- ladder resonator側パラメータ

特に finger pairs や reflector pairs は整数であり、
period や aperture と同じ方法で扱うと探索効率が落ちる。

---

### 3.3 高次元化に弱い

たとえば、

```text
center_outer_same = True
```

では center と outer の設計変数を共有できるため探索次元は比較的小さい。

一方、

```text
center_outer_same = False
```

では center / outer を独立に最適化するため、
設計自由度が大きく増加する。

最初から全自由度を開放すると、探索空間が急激に大きくなり、
DEの収束速度が低下する可能性が高い。

---

### 3.4 penalty weight への依存

仕様違反に対して、

```text
score =
    performance
    + penalty_weight × violation
```

のようにすると、

```text
penalty_weight = 10
penalty_weight = 100
penalty_weight = 1000
```

の選び方によって探索結果が変わりやすい。

---

## 4. 推奨方針

標準DEを別アルゴリズムに全面置換するのではなく、

> **DEをSAW構造探索向けに強化する**

方針を採る。

推奨構成は以下。

```text
L-SHADE
  +
SAW構造の階層探索
  +
feasibility-first 制約処理
  +
整数近傍探索
  +
最終局所最適化
```

---

# 5. L-SHADE系DEへの変更

## 5.1 概要

標準DEの代わりに、

```text
L-SHADE
```

またはそれに近い適応型DEを採用する。

L-SHADEでは主に以下を行う。

1. mutation scale `F` の適応
2. crossover rate `CR` の適応
3. population size の段階的縮小
4. `current-to-pbest/1` 系 mutation
5. 成功した探索履歴の利用

---

## 5.2 F / CR の自己適応

通常DEでは、

```python
F = 0.7
CR = 0.9
```

などを固定する。

L-SHADEでは、過去に改善に成功した `F` と `CR` を記録し、
次世代の個体生成に利用する。

これにより、

```text
探索初期
  ↓
大きな移動

探索中盤
  ↓
探索と収束のバランス

探索終盤
  ↓
局所的な微調整
```

へ自動的に変化させられる。

---

## 5.3 current-to-pbest/1

推奨 mutation は概念的に以下。

\[
x_i'
=
x_i
+
F(x_{pbest}-x_i)
+
F(x_{r1}-x_{r2})
\]

意味としては、

```text
現在の個体
   +
良い個体方向への移動
   +
多様性を保つランダム差分
```

となる。

SAW設計では、良好な構造が見つかり始めた後に
その傾向を利用できるため、純粋な `DE/rand/1/bin` より効率的である可能性が高い。

---

## 5.4 Population size の縮小

探索初期は個体数を多くし、
探索終盤は個体数を減らす。

例：

```text
Generation 0
population = 200

        ↓

中盤
population = 100

        ↓

終盤
population = 30
```

これにより、

- 初期：探索多様性を確保
- 終盤：COM評価回数を削減しながら収束

が可能になる。

---

# 6. SAW-aware 階層探索

L-SHADEを単純に使うだけではなく、
SAW構造の階層性を探索アルゴリズムに利用する。

---

## 6.1 変数グループの例

```text
DMS center
  ├ period
  ├ aperture
  ├ finger pairs
  └ gap

DMS outer
  ├ period
  ├ aperture
  ├ finger pairs
  └ gap

Reflector
  ├ period
  └ pairs

Ladder resonator
  ├ series resonator parameters
  └ shunt resonator parameters
```

---

# 7. center_outer_same を利用した二段階探索

このプロジェクトで特に有効と考える改良。

---

## Phase 1: 低自由度探索

まず、

```text
center_outer_same = True
```

として、

\[
x_{\mathrm{center}}
=
x_{\mathrm{outer}}
\]

の制約を入れる。

### 目的

- 探索次元を減らす
- 大まかな良好領域を高速に発見する
- 無駄な自由度を抑える

### 使用アルゴリズム

```text
L-SHADE
```

---

## Phase 2: 全自由度探索

Phase 1で得られた最良解を使って、

```text
center_outer_same = False
```

へ切り替える。

これにより、

\[
x_{\mathrm{center}}
\neq
x_{\mathrm{outer}}
\]

を許可する。

### 初期Population

Phase 1の最良解を中心として、
小さな摂動を与えた個体を生成する。

例：

```text
Phase1 best
    ↓
center = base + small perturbation
outer  = base + small perturbation
```

### 利点

```text
低自由度空間
   ↓
良い領域発見
   ↓
自由度を開放
   ↓
局所的に高精度探索
```

となり、最初から高次元探索するより効率が良い。

---

# 8. Feasibility-first 制約処理

penalty weight依存を減らすため、
設計候補の比較規則を明示的にする。

---

## 8.1 比較ルール

候補 A と B を比較する場合：

```text
Aのみ仕様内
→ Aを採用

Bのみ仕様内
→ Bを採用

両方仕様外
→ 制約違反量が小さい方

両方仕様内
→ 本来の性能scoreが良い方
```

すなわち、

\[
\mathrm{feasible}
>
\mathrm{infeasible}
\]

を基本ルールとする。

---

## 8.2 制約違反量

例：

\[
V =
w_1 V_{\mathrm{IL}}
+
w_2 V_{\mathrm{RL}}
+
w_3 V_{\mathrm{stopband}}
+
w_4 V_{\mathrm{bandwidth}}
\]

ただし `V` は性能評価値ではなく、
仕様違反の程度を表す指標として使用する。

性能そのもののスコアと分離することが重要。

---

# 9. 整数変数の近傍探索

以下のような変数は整数。

- finger pairs
- reflector pairs
- resonator finger count
- section count 等

DE内部で丸めるだけではなく、
グローバル探索終了後に整数近傍探索を追加する。

---

## 9.1 例

L-SHADEの解：

```text
center fingers = 41
outer fingers  = 36
reflector pairs = 52
```

周辺候補：

```text
center:
39, 40, 41, 42, 43

outer:
34, 35, 36, 37, 38

reflector:
50, 51, 52, 53, 54
```

ただし全組み合わせ総当たりではなく、
以下のように限定する。

```text
1変数ずつ近傍探索
      ↓
改善した方向のみ維持
      ↓
必要なら2変数組み合わせを確認
```

---

# 10. Continuous Polish

整数変数を決定した後、
連続変数のみを局所最適化する。

推奨：

```text
Powell
```

または必要に応じて、

```text
SLSQP
```

---

## 10.1 流れ

```text
L-SHADE
   ↓
integer refinement
   ↓
整数変数を固定
   ↓
continuous variables
   ↓
Powell
```

対象例：

```text
period
aperture
gap
coupling length
reflector period
etc.
```

---

## 10.2 役割分担

```text
L-SHADE
→ 良い谷を探す

Integer refinement
→ 離散変数を調整

Powell
→ 谷の底を細かく探す
```

このような構成は、
グローバル探索とローカル探索を組み合わせる
memetic optimization に近い。

---

# 11. 周波数グリッドの段階化

最適化全段階でdense gridを使うと計算負荷が高い。

そのため以下を推奨する。

---

## Stage A

```text
coarse frequency grid
```

L-SHADEの初期探索に使用。

---

## Stage B

良い個体だけ、

```text
medium grid
```

で再評価。

---

## Stage C

最終候補だけ、

```text
dense grid
```

で評価する。

---

## Stage D

dense gridで仕様違反が発生した場合、

```text
再最適化
```

を行う。

---

# 12. 推奨する最終探索フロー

```text
Topology / wiring 候補
        │
        ▼
┌────────────────────────────┐
│ Phase 1                    │
│ Reduced DOF                │
│ center_outer_same = True   │
│                            │
│ L-SHADE                    │
│ coarse frequency grid      │
└─────────────┬──────────────┘
              │
              ▼
        Phase 1 best
              │
              ▼
┌────────────────────────────┐
│ Phase 2                    │
│ Full DOF                   │
│ center_outer_same = False  │
│                            │
│ Phase1 bestをseed          │
│ L-SHADE                    │
│ coarse / medium grid       │
└─────────────┬──────────────┘
              │
              ▼
        dense frequency
          validation
              │
              ▼
┌────────────────────────────┐
│ Integer refinement         │
│                            │
│ finger ±1, ±2              │
│ reflector ±1, ±2           │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│ Continuous polish          │
│                            │
│ Powell                     │
│ 整数変数は固定             │
└─────────────┬──────────────┘
              │
              ▼
       Final dense evaluation
              │
              ▼
          最終設計候補
```

---

# 13. 全段階で使用する制約処理

以下を基本とする。

```text
feasibility-first
```

比較優先順位：

```text
1. 仕様内かどうか
2. 制約違反量
3. 本来の性能score
```

---

# 14. 推奨実装優先度

| 改良項目 | 効果期待 | 実装難度 | 優先度 |
|---|---:|---:|---:|
| SHADE / L-SHADE化 | ★★★★★ | 中 | 最優先 |
| feasibility-first | ★★★★★ | 低〜中 | 最優先 |
| center_outer_same の段階探索 | ★★★★★ | 低 | 最優先 |
| 整数近傍探索 | ★★★★☆ | 低 | 高 |
| Powell polish | ★★★☆☆ | 低 | 高 |
| adaptive frequency grid | ★★★★☆ | 中 | 高 |
| surrogate model | ★★★★☆ | 高 | 後回し |
| CMA-ESへの全面変更 | ★★★☆☆ | 中 | 現時点では不要 |
| Bayesian Optimization | ★★☆☆☆ | 高 | SAW構造探索では低優先 |

---

# 15. 推奨実装順序

## Step 1

現行DEを維持したまま、

```text
feasibility-first
```

を追加する。

---

## Step 2

```text
center_outer_same = True
        ↓
center_outer_same = False
```

の二段階探索を追加する。

---

## Step 3

標準DEを、

```text
SHADE / L-SHADE
```

へ変更する。

---

## Step 4

整数近傍探索を追加する。

---

## Step 5

Powellによるcontinuous polishを追加する。

---

## Step 6

周波数gridを、

```text
coarse
→ medium
→ dense
```

へ適応化する。

---

# 16. 当面の推奨アルゴリズム

最終的には以下を標準構成とする。

```text
Reduced-DOF L-SHADE
        ↓
Full-DOF L-SHADE
        ↓
Dense validation
        ↓
Integer neighborhood refinement
        ↓
Powell continuous polish
        ↓
Final dense evaluation
```

制約処理：

```text
feasibility-first
```

---

# 17. 結論

今回のSAW構造最適化では、
別の最適化アルゴリズムへ全面的に移行するよりも、

```text
標準DE
   ↓
L-SHADE
   +
SAW構造の階層性
   +
feasibility-first
   +
integer refinement
   +
local polish
```

へ発展させる方が適している。

特に重要なのは、

```text
center_outer_same = True
```

で低次元探索を行った後、

```text
center_outer_same = False
```

へ自由度を開放する二段階探索である。

これはSAW構造そのものの階層性を利用した探索であり、
単純な汎用最適化より高い探索効率が期待できる。

今後の実装ではまず、

1. feasibility-first
2. center / outer 二段階探索
3. L-SHADE化

の3点を優先して導入する。
