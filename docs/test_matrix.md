# EncodeLab 互換性テストマトリクス

対象プリセット: **H.264 — Compatible (Discord / PowerPoint)**
出力仕様: MP4 / H.264 High 4.1 / yuv420p / CFR / `-movflags +faststart` / `-an`

---

## 再生環境別チェックリスト

### Windows

| 環境 | 基本再生 | シーク | サムネイル | ループ | 備考 |
|------|---------|-------|-----------|-------|------|
| Windows Media Player (WMP) | □ | □ | □ | □ | 最低限の互換性基準 |
| Movies & TV (Films & TV) | □ | □ | □ | □ | Windows 10/11 標準 |
| エクスプローラー プレビュー | □ | — | □ | — | サムネイルが生成されるか |
| VLC | □ | □ | □ | □ | 参照用 (VLC は何でも再生する) |

### macOS

| 環境 | 基本再生 | シーク | サムネイル | ループ | 備考 |
|------|---------|-------|-----------|-------|------|
| QuickTime Player | □ | □ | □ | □ | 最重要。音声なし MP4 の可否確認 |
| Finder プレビュー (スペースキー) | □ | — | □ | — | Space キーでプレビューが出るか |
| IINA | □ | □ | □ | □ | 参照用 |

### ブラウザ

| 環境 | `<video>` タグ再生 | 自動再生 | シーク | 備考 |
|------|------------------|---------|-------|------|
| Chrome (Windows) | □ | □ | □ | |
| Edge (Windows) | □ | □ | □ | |
| Firefox (Windows) | □ | □ | □ | |
| Safari (macOS) | □ | □ | □ | QuickTime エンジン使用 |
| Chrome (Android) | □ | □ | □ | モバイル再生確認 |

### Discord

| チェック項目 | 結果 | 備考 |
|------------|------|------|
| ファイルアップロード成功 (< 25 MB) | □ | Free プランの上限 |
| チャット内プレビュー表示 | □ | サムネイルとプレイヤーが出るか |
| プレイヤー再生 | □ | |
| プレイヤーでシーク | □ | |
| Nitro でのアップロード (< 500 MB) | □ | |

### PowerPoint

| チェック項目 | 結果 | 備考 |
|------------|------|------|
| ファイル → 挿入 → ビデオ → このデバイス | □ | |
| 挿入後にスライド上で再生 | □ | |
| スライドショー中に再生 | □ | 最重要 |
| 自動再生設定 | □ | アニメーションタブで「自動」に設定 |
| ループ再生設定 | □ | |
| 「ビデオを最適化」ダイアログが出ないか | □ | 出た場合は互換性問題の可能性 |
| PPTX を PDF にエクスポート | □ | 動画はリンク切れになって正常 |
| 別 PC で PPTX を開いて再生 | □ | ファイル埋め込み確認 |
| PowerPoint for Mac で再生 | □ | Windows 版と Mac 版で差があることがある |

---

## ffmpeg コマンドで確認すべき出力属性

変換後に ffprobe で以下を確認する:

```bash
ffprobe -v quiet -print_format json -show_streams -show_format output.mp4
```

| 属性 | 期待値 | 確認コマンド |
|------|--------|------------|
| `codec_name` | `h264` | `streams[0].codec_name` |
| `profile` | `High` | `streams[0].profile` |
| `level` | `41` | `streams[0].level` |
| `pix_fmt` | `yuv420p` | `streams[0].pix_fmt` |
| `r_frame_rate` | `15/1` など整数比 | `streams[0].r_frame_rate` |
| `avg_frame_rate` | `r_frame_rate` と一致 (CFR 確認) | `streams[0].avg_frame_rate` |
| 音声ストリーム数 | `0` (ソース無音声の場合) | `nb_streams` |
| `format_name` | `mov,mp4,m4a,3gp,3g2,mj2` | `format.format_name` |

CFR の確認:
```bash
ffprobe -select_streams v -show_entries stream=r_frame_rate,avg_frame_rate output.mp4
```
`r_frame_rate` と `avg_frame_rate` が一致していれば CFR。

faststart の確認 (moov atom が先頭にあるか):
```bash
ffprobe -v trace output.mp4 2>&1 | head -20
```
`moov` が `mdat` より前に現れれば faststart 有効。

---

## 既知の問題と回避策

### PowerPoint で再生できない場合

1. **Windows のコーデックパックが古い** → Windows Update または `wmic qfe list` で KB 確認
2. **PowerPoint 2013 以下** → H.264 Level 3.1 (1280×720 以下) でないと再生不可な場合がある
3. **音声なし MP4 で "メディアが見つかりません"** → 現代 PowerPoint では発生しないが、発生した場合は silent AAC トラック追加を検討

### QuickTime で再生できない場合

1. **10-bit** → yuv420p が正しく適用されているか ffprobe で確認
2. **奇数解像度** → video_filter の `scale=trunc(iw/2)*2:trunc(ih/2)*2` が効いているか確認

### Discord でプレビューが出ない場合

1. **ファイルサイズが 25 MB 超** → CRF を上げる (26〜28 程度) か解像度を下げる
2. **duration_ts が異常** → rawvideo 変換後は正常になるはず

---

## Ultra Safe 将来プリセット (参考)

現設計で以下のプリセットを将来追加できる:

```python
"H.264 — Ultra Safe": PresetConfig(
    video_codec="libx264",
    video_profile="main",   # Baseline の次に互換性が高い
    video_level="3.1",      # 1280×720@30fps 上限。最古の HW デコーダーでも動作
    force_cfr=True,
    pix_fmt="yuv420p",
    video_filter="scale=trunc(iw/2)*2:trunc(ih/2)*2",
    encoder_preset="medium",
    audio_codec="aac",
    audio_bitrate="128k",
    output_flags=("-movflags", "+faststart"),
    # 将来追加予定:
    # add_silent_audio=True,  # 音声なしソースでも AAC トラックを生成
    # max_bitrate="4M",       # PowerPoint が推奨する上限
)
```

`add_silent_audio` が必要になった場合は `PresetConfig` に `bool` フィールドを追加し、
`build_ffmpeg_command()` で `-f lavfi -i anullsrc` を第2入力として挿入する。
現在の単一 `-i` 入力設計はこの変更に耐えられる。
