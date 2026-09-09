# SAW COM インピーダンス探索プロトタイプ

## フォルダ構成

| フォルダ | 用途 | 最初に読むファイル |
|---|---|---|
| `configs/` | COMモデル、基本仕様、試行別探索条件 | `configs/README.md` |
| `src/` | COM計算、回路、最適化、レポート生成 | `src/README.md` |
| `scripts/` | 共通起動処理、試行ランチャー、解析、保守 | `scripts/README.md` |
| `tests/` | 単体・統合テスト | `tests/README.md` |
| `docs/` | 規約、ガイド、結果、計画レビュー | `docs/README.md` |
| `runs/` | 試行ごとの生成結果。整理・移動の対象外 | 各runの `report.html` と `manifest.json` |

通常の流れは、`configs/studies/` から試行設定を選び、対応する `scripts/launchers/` を実行し、`runs/` のレポートを確認する。実装を変更した場合は `tests/` を実行する。

## Stage 2: DMS＋ラダー共振子のインピーダンス探索

Stage 1/2の指示書と `saw_com_codex_handoff`、`saw_com_codex_stage2_handoff` の参照パッチを統合済みです。50 Ωを基準に、DMS単独と直列・並列COM共振子を含む構成を、結線との組み合わせで比較します。

```powershell
# 短時間の動作・探索確認（20/50/100 Ω、3構成、3結線、3シード）
./saw-com-optimizer/scripts/launchers/stage2-study.ps1 --config configs/studies/stage2_pilot.yaml --run runs/stage2-pilot-v1

# 保存済み結果からレポートだけ再生成
./saw-com-optimizer/scripts/launchers/stage2-study.ps1 --config configs/studies/stage2_pilot.yaml --run runs/stage2-pilot-v1 --report-only

# 本探索。計算量が非常に大きいため、予算と構成を確認して新しいrun名で実行
./saw-com-optimizer/scripts/launchers/stage2-study.ps1 --config configs/studies/stage2_full.yaml --run runs/stage2-full-v1
```

パイロット結果は `runs/stage2-pilot-v1/report.html`、実装と検証の詳細は `docs/guides/stage2_implementation.md` にあります。スクリプトの分類は `scripts/README.md`、文書の分類は `docs/README.md` を参照してください。パイロットは探索予算が小さく全候補が仕様未達なので、最適インピーダンスの結論には使えません。

## 50 Ω固定のハイブリッド探索（追加機能）

```powershell
# このディレクトリの親から実行
./saw-com-optimizer/scripts/launchers/hybrid-50ohm.ps1 --run runs/hybrid-50ohm
./saw-com-optimizer/scripts/launchers/hybrid-50ohm.ps1 --run runs/hybrid-50ohm --report-only
```

通常Python環境ではこのディレクトリから `python -m sawopt.optimization.hybrid_study --run runs/hybrid-50ohm`。
設定は `configs/studies/hybrid_50ohm.yaml`、結果は `runs/hybrid-50ohm/report.html` です。

DMS単独の3結線を各3シードで比較後、最良の結線に直列・並列COM共振子を最大2個追加する12構成を比較します。上位3構成とDMS単独を追加探索します。全段階でRs=Rl=50 Ωです。詳細は `docs/guides/hybrid_50ohm.md`。

この拡張によりコード指紋が変わったため、以前のrunは閲覧用に保持し、再計算時は新しいrun名を使用してください。新しいハイブリッドrunは同一設定・コードで完了済み試行を再利用します。

## Stage 3.1: 50 Ω DMS収束証明

Stage 3.1 は `maxiter` 倍率ではなく、一意にデコードされた設計数
`500/1000/2000/4000` を予算として、`outer_ports` と
`center_outer_same` を同一 cold seed で比較します。予算・適応ラウンド・
best-so-far・polish・増分診断は各 trial JSON と集計 CSV に保存されます。

```powershell
$env:PYTHONPATH = "./src"
python -m sawopt.optimization.convergence_study `
  --config configs/studies/stage3_convergence_50ohm.yaml `
  --run runs/stage3_1_50ohm
python -m sawopt.reporting.review_bundle `
  --run runs/stage3_1_50ohm `
  --output review_bundles/stage3_1_50ohm_review.zip
```

レビュー bundle の作成前に、run 内の `tests/pytest.txt` と
`tests/pytest_summary.json` にレビュー対象ソースのテスト結果を配置します。
`--include-history` と `--include-npz` は大容量データを含める場合だけ指定します。

左右対称3-IDTを仮COM定数で計算し、各終端抵抗に対して寸法を再最適化するPython CLIです。**実製品の最適インピーダンスを示すものではありません。** 計画書の確認結果は [初期計画レビュー](docs/reviews/review_ja.md)。

## このPCで実行

作業フォルダ `saw-com-optimizer` の親からPowerShellで実行します。`scripts/launchers/base-study.ps1` は共通起動処理を介して、このPCの同梱Pythonと親フォルダ `.deps` を使用します。

```powershell
./saw-com-optimizer/scripts/launchers/base-study.ps1 simulate --run runs/baseline
./saw-com-optimizer/scripts/launchers/base-study.ps1 optimize --rs 50 --rl 50 --run runs/50ohm
./saw-com-optimizer/scripts/launchers/base-study.ps1 sweep --run runs/prototype --refine-step 5
./saw-com-optimizer/scripts/launchers/base-study.ps1 report --run runs/prototype
```

`runs/prototype/report.html` をブラウザで開くと比較図を確認できます。全阻止帯域・寸法・シード幅は `comparison.csv`、各候補の周波数応答はNPZ、各評価履歴はJSONLです。reportコマンドは保存済みデータだけを使います。

納品時の追加探索結果は **`runs/refined-prototype/report.html`** です。製造可能な初期集団を使い、次のコマンドで20世代まで探索しています。

```powershell
./saw-com-optimizer/scripts/launchers/base-study.ps1 sweep --run runs/refined-prototype --refine-step 5 --maxiter 20
```

初期試行の `runs/prototype` は旧コードによる比較用の記録です。現在のコードでは指紋が一致しないため再開せず、新しいrun名を使用してください。

## 別環境での再現

Python 3.11以上で、このディレクトリをカレントにします。

```shell
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m sawopt simulate --run runs/baseline
python -m sawopt optimize --rs 50 --rl 50 --run runs/50ohm
python -m sawopt sweep --run runs/prototype --refine-step 5
python -m sawopt report --run runs/prototype
```

基準設定は `configs/base/b28_dms_baseline.yaml`、COM仮定数は `configs/models/com_params_hypothetical.yaml`。探索は標準14個体×初期世代+4世代×3シードで、短時間の動作確認用です。`--maxiter 100` などで増やす場合は新しい `--run` を指定してください。抵抗点・シード・仕様・重み・製造制約はYAMLで変更できます。7変数の境界は `src/sawopt/core/models.py` の BOUNDS、固定メタライゼーション/膜厚比はFilterDesignにあります。一般的な設定差し替え機能の全実装ではありません。

同じコマンドとrunを再実行すると完了済みシードを再利用します。中断中のシードは初めからやり直し、履歴に追記します。設定指紋が異なるrunへの追記は拒否します。チェックポイントは最良設計の救済保存で、DE乱数状態の復元ではありません。

最適化で製造制約違反を事前拒否し、失敗を有限のペナルティとして記録します。採用候補は5000点超+適応細分化で再評価します。単一モード、固定材料、位相原点の理想化、寄生回路省略のため、実測/FEMを取り込むまでは実用設計値として扱えません。中央IDTは `center: grounded` または `floating`。Rs/Rlは別値でもAPIで評価可能ですが、標準スイープは同じ抵抗です。

計画書との差分: 並列探索と厳密な世代途中再開、全COM条件数、実測との一致、実装済みの寄生回路は未提供。物理検証に通る試作エンジンと探索フローを提供します。規約は `docs/conventions/com_convention.md` と `docs/conventions/network_convention.md` に記載しています。
