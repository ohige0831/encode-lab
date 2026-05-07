# EncodeLab — 仕様書

## 概要

EncodeLab は ffmpeg をバックエンドに使用した Windows 向けの軽量 GUI 動画コンバーターです。
ドラッグ&ドロップでファイルを投入し、プリセットを選択してワンクリックで変換できます。

- バージョン: 0.1.0
- GUI フレームワーク: PySide6 (Qt for Python)
- 対象 OS: Windows (主要ターゲット)
- 外部依存: ffmpeg / ffprobe (PATH 上に配置、または同梱)

---

## アーキテクチャ

```
encode-lab/
├── main.py                 エントリーポイント
├── ui/
│   ├── main_window.py      メインウィンドウ (レイアウト・シグナル配線)
│   ├── drop_zone.py        ドラッグ&ドロップ受付ウィジェット
│   ├── file_list.py        ファイルキュー表 (QTreeWidget ベース)
│   ├── advanced_panel.py   詳細設定パネル (折りたたみ式)
│   └── log_panel.py        ログ出力パネル
└── logic/
    ├── presets.py          プリセット定義・レジストリ
    ├── converter.py        ffmpeg コマンド生成・実行エンジン
    ├── worker.py           バックグラウンド変換スレッド
    ├── probe_worker.py     バックグラウンド ffprobe スレッド
    ├── ffprobe_reader.py   ffprobe 呼び出しとメディア情報パーサー
    ├── environment.py      ffmpeg/ffprobe の PATH チェック・GPU エンコーダー検出
    └── size_estimator.py   出力ファイルサイズ推定
```

UI と core logic は明確に分離されており、`logic/` に Qt のインポートは存在しません。

---

## エントリーポイント — `main.py`

| 関数 | 役割 |
|------|------|
| `_prepend_bundled_ffmpeg()` | PyInstaller でフリーズされた場合に `dist/EncodeLab/ffmpeg/` を PATH へ追加 |
| `main()` | QApplication 生成 → MainWindow 表示 → イベントループ開始 |

---

## UI レイヤー

### `ui/main_window.py` — `MainWindow`

アプリ全体の司令塔。子ウィジェットの組み立て、シグナルの配線、ワーカーのライフサイクル管理を担う。

**レイアウト (上から順)**

1. `DropZone` — ファイル投入エリア
2. `FileListWidget` — キュー表示テーブル
3. プリセット選択行 (コンボボックス + オーディオ ON/OFF + 説明ラベル + サイズ推定ラベル)
4. 区切り線
5. `AdvancedPanel` — 詳細設定 (折りたたみ)
6. `LogPanel` — ログ
7. プログレスバー (変換中のみ表示)
8. Convert / Cancel ボタン行
9. ステータスバー

**主要メソッド**

| メソッド | 役割 |
|----------|------|
| `_collect_settings()` | UI の状態を `ConversionSettings` に集約 |
| `_run_environment_check()` | ffmpeg/ffprobe の存在と GPU エンコーダーの可否を検証 |
| `_start_probe(paths)` | `ProbeWorker` を起動し完了後に自己追跡セットから除去 |
| `_on_convert_clicked()` | ジョブリストを構築し `ConversionWorker` を起動 |
| `_set_running_state(running)` | 変換中 / 待機中でコントロールの有効・表示を切り替え |
| `_update_size_estimate()` | 全キューファイルの合計デュレーションからサイズ推定を更新 |

**シグナルフロー**

```
DropZone.files_dropped
  → _on_files_dropped → FileListWidget.add_files + ProbeWorker 起動

ProbeWorker.file_probed
  → _on_file_probed → FileListWidget.set_item_media_info + サイズ推定更新

ConversionWorker.job_started / job_progress / job_finished / job_failed
  → 各スロットでプログレスバー・ログ・ファイルリストのステータスを更新

ConversionWorker.all_done → _on_all_done → UI をアイドル状態へ復帰
```

---

### `ui/drop_zone.py` — `DropZone`

| シグナル | 型 | 説明 |
|----------|----|------|
| `files_dropped` | `list[Path]` | サポート済み拡張子のファイルがドロップされたとき発火 |

- `SUPPORTED_EXTENSIONS` でフィルタリング (大文字小文字を区別しない)
- ドラッグ中は枠色とバックグラウンド色が変化

---

### `ui/file_list.py` — `FileListWidget`

QTreeWidget ベースのキュー表。列は固定5本:

| 列 | 内容 | リサイズ方式 |
|----|------|------------|
| File | ファイル名 | Stretch |
| Duration | 再生時間 (`ffprobe` 取得後に更新) | Fixed 70px |
| Resolution | 解像度 (`ffprobe` 取得後) | Fixed 100px |
| Codec | 動画コーデック名 | Fixed 70px |
| Status | queued / running… / done / failed | Fixed 80px |

`JobStatus` 列挙型のステータスごとに色が異なる (灰 / 青 / 緑 / 赤)。

---

### `ui/advanced_panel.py` — `AdvancedPanel`

折りたたみ可能な詳細設定パネル。アニメーション付き (200 ms / InOutCubic)。

| フィールド | 型 | デフォルト |
|------------|----|----------|
| CRF | QSpinBox (0–63) | プリセットに依存 |
| Video bitrate | QLineEdit | 空 (CRF 優先) |
| Resolution | QLineEdit | 空 (ソースを維持) |
| Extra flags | QLineEdit | 空 |
| Output dir | QLineEdit + Browse ボタン | 空 (ソースと同フォルダ) |

- `apply_preset_defaults(config)`: プリセット切り替え時に CRF スピナーを更新。GPU プリセット等 CRF 非対応のコーデックはスピナーを無効化しツールチップで理由を表示。
- `settings_changed` シグナル: bitrate / CRF の変更時に発火 → `MainWindow` がサイズ推定を再計算。

---

### `ui/log_panel.py` — `LogPanel`

読み取り専用のスクロール可能ログエリア。HTML ベースのカラーリング。

| メソッド | ラベル | 色 |
|----------|--------|-----|
| `append_command(cmd)` | `[CMD]` | 灰 |
| `append_info(msg)` | `[INFO]` | 青 |
| `append_success(msg)` | `[OK]` | 緑 |
| `append_error(msg)` | `[ERROR]` | 赤 |
| `append_warning(msg)` | `[WARN]` | 黄 |

---

## Logic レイヤー

### `logic/presets.py`

プリセットの唯一の真実の源 (Single Source of Truth)。

**定数**

| 定数 | 内容 |
|------|------|
| `SUPPORTED_EXTENSIONS` | 受付可能な入力拡張子集合 (14 種) |
| `QUALITY_CRF` | 品質ティア別 CRF デフォルト値 |

```python
QUALITY_CRF = {
    "high_quality": 18,  # 視覚的にほぼロスレス
    "standard":     23,  # ffmpeg デフォルト
    "lightweight":  32,  # 小ファイル優先
}
```

**`PresetConfig` データクラス (frozen)**

| フィールド | 型 | 説明 |
|------------|----|------|
| `name` | `str` | コンボボックス表示名 |
| `description` | `str` | UI に表示される一行説明 |
| `quality_mode` | `str` | 品質制御方式の短縮説明 |
| `video_codec` | `str` | `-vcodec` に渡す値 |
| `audio_codec` | `str` | `-acodec` に渡す値 (空 = 音声なし) |
| `crf` | `int` | デフォルト CRF (0 = 非適用) |
| `encoder_preset` | `str` | `-preset` に渡す値 (空 = 省略) |
| `container` | `str` | 出力拡張子 (例: `.mp4`) |
| `uses_gpu` | `bool` | GPU (NVENC) プリセット判定フラグ |
| `extra_video_flags` | `tuple[str, ...]` | `-vcodec` 直後に挿入する追加フラグ |
| `pix_fmt` | `str` | `-pix_fmt` の値 (空 = 省略) |
| `video_filter` | `str` | `-vf` の値 (空 = 省略) |
| `audio_bitrate` | `str` | `-b:a` の値 (空 = 省略) |
| `output_flags` | `tuple[str, ...]` | 出力パス直前に挿入するフラグ |

**登録済みプリセット一覧**

| プリセット名 | コーデック | コンテナ | GPU |
|-------------|-----------|---------|-----|
| H.264 — Compatible (Discord / PowerPoint) | libx264 (profile:high / level 4.1 / yuv420p / faststart) | .mp4 | |
| H.264 — Fast (web) | libx264 / fast | .mp4 | |
| H.264 — High quality | libx264 / slow / CRF 18 | .mp4 | |
| H.265 / HEVC — Balanced | libx265 / medium | .mp4 | |
| H.265 / HEVC — Small file | libx265 / slow / CRF 32 | .mp4 | |
| AV1 — High efficiency | libsvtav1 + libopus | .mp4 | |
| ProRes 422 — Editing | prores_ks (profile 2) + pcm_s16le | .mov | |
| GIF — Animated | gif (音声なし) | .gif | |
| H.264 NVENC — Fast web | h264_nvenc / VBR CQ 23 | .mp4 | ✓ |
| HEVC NVENC — Compact | hevc_nvenc / VBR CQ 23 | .mp4 | ✓ |

---

### `logic/converter.py`

**データ型**

`ConversionSettings` — UI から集めたフラットな設定バッグ

| フィールド | デフォルト | 説明 |
|-----------|-----------|------|
| `preset` | (必須) | `PRESETS` のキー |
| `audio_enabled` | `True` | 音声を含めるか |
| `crf` | 23 | CRF 値 |
| `bitrate` | `""` | ビットレート文字列 (非空でCRF上書き) |
| `resolution` | `""` | 出力解像度 (空=ソース維持) |
| `extra_flags` | `""` | 生の ffmpeg フラグ |
| `output_dir` | `""` | 出力ディレクトリ (空=ソースと同フォルダ) |

`ConversionJob` — 1 ファイル分の変換ジョブ

| フィールド | 説明 |
|-----------|------|
| `input_path` | 入力ファイルパス |
| `settings` | ConversionSettings |
| `duration_sec` | ffprobe で取得した長さ (進捗計算に使用) |
| `output_path` | `__post_init__` で自動導出 |

**出力パス命名規則**

1. `<stem>_converted<ext>` を試みる
2. 衝突した場合は `<stem>_converted_01<ext>` … `_converted_99<ext>` を試みる
3. 全スロット使用済みの場合はベース名にフォールバック (`-y` で上書き)

**`build_ffmpeg_command(job)` — コマンドビルダー**

副作用なし。argv リストを返す。フラグ挿入順:

```
ffmpeg -y -i <input>
  -vcodec <codec>
  [extra_video_flags]
  [-pix_fmt ...]
  [-b:v ... | -crf ...]
  [-preset ...]
  [-vf ...]
  [-an | -acodec ... [-b:a ...]]
  [extra_flags]
  [output_flags]
  <output>
```

**`stream_job(job)` — ストリーミング実行**

ジェネレーター。ffmpeg を `Popen` で起動し、stderr の `time=` 行をパースして進捗を 0–100 の int で yield する。

- 0: プロセス起動直後
- 1–99: ffmpeg の `time=HH:MM:SS.frac` から計算
- 100: ffmpeg が正常終了 (exit code 0)
- キャンセル: ループを break すると `GeneratorExit` 経由で ffmpeg を `terminate()` → `wait()`
- 失敗: exit code ≠ 0 → `ConversionError` を raise (stderr 全文を含む)

**進捗パース**

```
_TIME_RE = re.compile(r"time=(\d+):(\d{2}):(\d{2})\.(\d+)")
percent = min(99, int(elapsed / total * 100))
```

負の timestamp (エンコード開始前に ffmpeg が出力する) は無視。

---

### `logic/worker.py` — `ConversionWorker`

QThread サブクラス。ジョブリストをバックグラウンドで逐次実行する。

**シグナル**

| シグナル | 引数 | タイミング |
|----------|------|----------|
| `job_started` | job | ffmpeg 起動直前 |
| `job_progress` | job, percent (int) | 進捗行ごと |
| `job_finished` | job | 正常完了時 |
| `job_failed` | job, error_message (str) | ConversionError 発生時 |
| `cancelled` | completed, total | キャンセル確定時 |
| `all_done` | successes, failures | 全ジョブ終了後 (キャンセル含む) |

**キャンセル機構**

`request_cancel()` でフラグを立てる。チェックはジョブ間と進捗ループ内の 2 箇所。現在の実装ではジョブ完了を待ってから停止する (ジョブ途中の即時停止は TODO)。

stderr のエラーメッセージは末尾 8 行のみ表示 (`_trim_stderr`)。

---

### `logic/probe_worker.py` — `ProbeWorker`

QThread サブクラス。ファイルリストを ffprobe で順次解析し、結果を逐次発火する。

| シグナル | 引数 | タイミング |
|----------|------|----------|
| `file_probed` | Path, MediaInfo | 1 ファイル解析完了ごと |
| `all_probed` | — | 全ファイル完了後 |

fire-and-forget 設計: `start()` を呼ぶだけでよい。

---

### `logic/ffprobe_reader.py`

**`MediaInfo` データクラス (frozen)**

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `duration_sec` | `float \| None` | 再生時間 (秒) |
| `width` | `int \| None` | 映像幅 |
| `height` | `int \| None` | 映像高さ |
| `video_codec` | `str \| None` | コーデック名 |

プロパティ: `duration_str` (例: `"1:23:45"`)、`resolution_str` (例: `"1920×1080"`)、`codec_str`

**`probe(path)` 関数**

- タイムアウト 10 秒
- 失敗・例外・タイムアウト時は全フィールド `None` の `MediaInfo()` を返す (例外を raise しない)
- JSON 形式で取得し最初の video ストリームを使用

---

### `logic/environment.py`

**`check_environment()` → `EnvironmentCheckResult`**

1. `shutil.which` で ffmpeg / ffprobe のパスを取得
2. `ffmpeg -encoders` を実行し `h264_nvenc` / `hevc_nvenc` の有無を確認

**`EnvironmentCheckResult` データクラス (frozen)**

| プロパティ | 説明 |
|-----------|------|
| `all_ok` | ffmpeg + ffprobe 両方存在する場合 True |
| `missing()` | 不在のツール名リスト |
| `gpu_encoder_available(codec)` | 指定コーデックが利用可能か |
| `user_message()` | ログパネル向けの平易なエラー文 |

起動時と変換ボタン押下時の 2 タイミングでチェックされる。

---

### `logic/size_estimator.py`

**`estimate_output_size(settings, config, total_duration_sec)` → `str`**

| 条件 | 返却値 |
|------|--------|
| bitrate 未指定 (CRF モード) | `"Estimated size: variable (CRF-based)"` |
| bitrate 指定 + デュレーション不明 | `"Estimated size: unavailable"` |
| bitrate 指定 + デュレーション既知 | `"Estimated size: ~X MB (approx.)"` |

音声ビットレートの推定値:

| コーデック | ビットレート |
|-----------|------------|
| pcm_s16le | 1,411,200 bps |
| pcm_s24le | 2,116,800 bps |
| pcm_s32le | 2,822,400 bps |
| AAC / libopus (その他) | 128,000 bps |

`parse_bitrate(s)` は `"4000k"` / `"4.5M"` 等の ffmpeg スタイルの文字列をパースする。

---

## データフロー図

```
[ユーザーがファイルをドロップ]
    ↓ DropZone.files_dropped
MainWindow._on_files_dropped
    ├─→ FileListWidget.add_files           (キューに追加)
    └─→ ProbeWorker.start()                (バックグラウンドで ffprobe)
            ↓ file_probed
        MainWindow._on_file_probed
            ├─→ FileListWidget.set_item_media_info
            └─→ MainWindow._update_size_estimate

[ユーザーが Convert をクリック]
    ↓
MainWindow._on_convert_clicked
    ├─→ check_environment()               (実行前チェック)
    ├─→ build_ffmpeg_command() x N        (コマンドをログ表示)
    └─→ ConversionWorker.start()          (バックグラウンドで変換)
            ↓ job_started / job_progress / job_finished / job_failed
        MainWindow の各スロット
            └─→ FileListWidget / LogPanel / ProgressBar 更新
            ↓ all_done
        MainWindow._on_all_done → UI をアイドル状態へ復帰
```

---

## 安全設計

- 元ファイルをデフォルトで上書きしない (出力パスは常に `_converted` サフィックス付き)
- ffmpeg コマンドに `shell=False` を使用 (コマンドインジェクション回避)
- Windows の `--windowed` ビルドで CMD フラッシュを抑制 (`CREATE_NO_WINDOW`)
- ffprobe は 10 秒タイムアウト付き

---

## 既知の TODO

| 箇所 | 内容 |
|------|------|
| `drop_zone.py` | マウスクリックで `QFileDialog` を開く機能 |
| `drop_zone.py` | 拒否されたファイル名をステータスバーやツールチップに表示 |
| `file_list.py` | Status 列にバッジ形スタイルのカスタムデリゲートを使用 |
| `advanced_panel.py` | CRF 非対応コーデック選択時に CRF 行を完全非表示 |
| `advanced_panel.py` | bitrate 文字列の入力バリデーション |
| `advanced_panel.py` | 解像度のドロップダウン提供 |
| `advanced_panel.py` | Extra flags がプリセット設定と競合する場合の警告 |
| `converter.py` | `-maxrate` / `-bufsize` による CBR/VBR 上限設定 |
| `converter.py` | 高品質ダウンスケール用 `:flags=lanczos` の追加 |
| `worker.py` | `stream_job` の `Popen` ハンドルを公開しジョブ途中の即時キャンセルを実現 |
| `main_window.py` | 全ジョブ成功時に「出力フォルダを開く」ショートカットを追加 |

---

## 依存関係

```
PySide6        GUI フレームワーク
ffmpeg         動画変換エンジン (外部バイナリ)
ffprobe        メディア情報取得 (外部バイナリ)
PyInstaller    実行ファイルのパッケージング
```
