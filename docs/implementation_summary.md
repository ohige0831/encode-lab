# EncodeLab 互換性強化 — 実装サマリー

## 変更ファイル一覧

| ファイル | 種別 | 変更内容 |
|----------|------|---------|
| `logic/presets.py` | 変更 | `PresetConfig` に `video_profile`/`video_level`/`is_recommended`/`force_cfr` を追加。Compatible プリセットを「推奨」に設定 |
| `logic/converter.py` | 変更 | `ConversionJob` に `has_audio` 追加。コマンドビルダーに profile/level emit・CFR・音声なし安全処理を追加 |
| `logic/ffprobe_reader.py` | 変更 | `MediaInfo` に `pix_fmt`/`has_audio_stream` を追加 |
| `logic/compatibility.py` | 新規 | rawvideo/bgr24/odd解像度などの危険フォーマット検出ロジック |
| `ui/main_window.py` | 変更 | 互換性警告のログ表示、`has_audio` の `ConversionJob` への連携、`is_recommended` 時の説明ラベル色変更 |
| `tests/conftest.py` | 新規 | pytest sys.path 設定 |
| `tests/test_converter.py` | 新規 | コマンド生成・profile汚染・音声処理テスト |
| `tests/test_compatibility.py` | 新規 | 警告検出・研究動画シナリオテスト |
| `tests/test_ffprobe_reader.py` | 新規 | MediaInfo パース・エッジケーステスト |
| `docs/test_matrix.md` | 新規 | 手動互換性テストチェックリスト |

---

## テスト結果

```
84 passed in 0.12s
```

全84テスト通過。

---

## 実際に生成される ffmpeg コマンド

### H.264 — Compatible (Discord / PowerPoint) — 音声なしソース

```
ffmpeg -y -i input.avi
  -vcodec libx264
  -profile:v high
  -level 4.1
  -pix_fmt yuv420p
  -crf 23
  -preset medium
  -vf scale=trunc(iw/2)*2:trunc(ih/2)*2
  -fps_mode cfr
  -an
  -movflags +faststart
  input_converted.mp4
```

### 研究動画への適用コマンド (参考)

```
ffmpeg -y -i "D:\yanase\original\20251127_upper_30mm_1st_top_25.avi"
  -vcodec libx264 -profile:v high -level 4.1
  -pix_fmt yuv420p -crf 23 -preset medium
  -vf scale=trunc(iw/2)*2:trunc(ih/2)*2
  -fps_mode cfr -an
  -movflags +faststart
  "D:\yanase\original\20251127_upper_30mm_1st_top_25_converted.mp4"
```

---

## 変換前 ffprobe (実測)

```
codec_name:     rawvideo
pix_fmt:        bgr24
width:          1280
height:         1024
r_frame_rate:   15/1
avg_frame_rate: 15/1
duration:       375.6 sec (6:15)
bit_rate:       ~472 Mbps
format_name:    avi
has_audio:      false
file_size:      ~22.2 GB (top) / ~22.1 GB (side)
```

## 変換後 ffprobe 確認コマンド

```bash
# 基本確認
ffprobe -v quiet -print_format json -show_streams -show_format output.mp4

# CFR確認 (r_frame_rate == avg_frame_rate なら CFR)
ffprobe -select_streams v -show_entries stream=r_frame_rate,avg_frame_rate output.mp4

# profile/level 確認
ffprobe -select_streams v -show_entries stream=codec_name,profile,level,pix_fmt output.mp4

# faststart確認 (moov が mdat より前に出ればOK)
ffprobe -v trace output.mp4 2>&1 | grep -E "^(moov|mdat)" | head -5
```

## 変換後の期待値

| 属性 | 期待値 |
|------|--------|
| `codec_name` | `h264` |
| `profile` | `High` |
| `level` | `41` |
| `pix_fmt` | `yuv420p` |
| `r_frame_rate` | `15/1` |
| `avg_frame_rate` | `15/1` (= r_frame_rate → CFR確認) |
| `has_audio` | `false` (ソースに音声なし) |
| `format_name` | `mov,mp4,...` |
| faststart | `moov` が `mdat` より前 |
| ファイルサイズ | CRF23 で数百 MB 程度 (元の約1/50以下) |

---

## 互換性上の意味

| フラグ | 理由 |
|--------|------|
| `-vcodec libx264` | H.264 ソフトウェアエンコーダー。最も広くサポートされる |
| `-profile:v high` | PowerPoint・QuickTime・Discord が対応する最高互換プロファイル |
| `-level 4.1` | 1920×1080@60fps まで対応。2010年以降のほぼすべての HW デコーダーで動作 |
| `-pix_fmt yuv420p` | 8bit YUV 4:2:0。bgr24・10bit・yuv444p 等の変換を強制。QuickTime の最大公約数フォーマット |
| `-crf 23` | 品質と圧縮のバランス。bitrate 依存ではなく視覚品質一定 |
| `-vf scale=trunc(iw/2)*2:trunc(ih/2)*2` | 奇数解像度を偶数に丸める。yuv420p の仕様要件 |
| `-fps_mode cfr` | VFR → CFR 変換。PowerPoint・Discord の VFR 再生バグを回避 |
| `-an` | 音声なしソースで `-acodec aac` を渡すと ffmpeg がエラー終了する問題を防止 |
| `-movflags +faststart` | moov atom を先頭に移動。ブラウザ・Discord のプログレッシブ再生・プレビューに必要 |

---

## 副作用リスク

| リスク | 評価 | 対策 |
|--------|------|------|
| ffmpeg 5.0 未満での `-fps_mode` 未知フラグエラー | 低 (Windows 11 + 現代 ffmpeg 前提) | `check_environment()` でバージョン確認を将来追加可能 |
| ProRes `-profile:v 2` と H.264 `video_profile` の意味の混在 | なし | ProRes は `extra_video_flags` に残し、`video_profile` 空で完全分離済み |
| `has_audio=None` (未プローブ) 時に `-acodec aac` で ffmpeg エラー | 低 (通常ファイルをドロップすれば自動プローブ) | ファイルをドロップしてから変換する通常フローでは必ずプローブ済み |
| `is_recommended` 色変更が GPU プリセットの赤/緑と競合 | なし | `elif config.is_recommended` で GPU チェックを優先する順序 |

---

## 未対応・将来検討項目

| 項目 | 優先度 | 概要 |
|------|--------|------|
| Silent AAC track | 低 | `add_silent_audio: bool` を `PresetConfig` に追加し `-f lavfi -i anullsrc` で対応。現代環境では不要 |
| `-fps_mode` バージョン検出 | 低 | `check_environment()` で ffmpeg バージョンを取得し、5.0未満では `-vsync cfr` にフォールバック |
| VFR ソースの検出 | 中 | `MediaInfo` に `is_vfr: bool` を追加。`r_frame_rate != avg_frame_rate` で判定し警告 |
| 最大解像度制限 | 低 | `max_resolution: str = ""` を PresetConfig に追加。Ultra Safe プリセット用 |
| `is_recommended` の UI バッジ | 低 | コンボボックスに `addItem(text, userData=name)` + `★` プレフィックス。現状は説明ラベルの青色で代替 |
| Odd resolution の自動補正警告 | 済 | `compatibility.py` で検出済み。Compatible プリセットの `-vf` で自動補正 |
