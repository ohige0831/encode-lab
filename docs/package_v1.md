# EncodeLab v1 パッケージング手順

## 方針

- ツール: **PyInstaller** による one-folder ビルド（`dist/EncodeLab/` フォルダ丸ごと配布）
- ffmpeg / ffprobe は **外部同梱方式**（アプリに同梱するが、バイナリ本体は配布者が別途用意して配置）
- ソースコードに対する変更は最小限（import パスの保持、Windows 固有の修正のみ）

---

## 前提条件

| ソフトウェア | バージョン |
|---|---|
| Python | 3.11 以上 |
| PySide6 | 6.6 以上 |
| PyInstaller | 6.x |
| ffmpeg / ffprobe | 任意の安定ビルド（配布者が別途用意） |

ffmpeg の入手先: <https://ffmpeg.org/download.html>  
Windows 向けには [BtbN ビルド](https://github.com/BtbN/FFmpeg-Builds/releases) が手軽です。

---

## ビルド手順

```powershell
# 1. encode-lab/ ディレクトリへ移動
cd Encode_Lab\encode-lab

# 2. 仮想環境を作成・有効化
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 依存パッケージをインストール
pip install -r requirements.txt
pip install pyinstaller

# 4. ビルド実行（spec ファイルを使う場合 — 推奨）
pyinstaller --noconfirm --clean EncodeLab.spec

# または spec を使わずに直接ビルドする場合
pyinstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name EncodeLab `
  --paths . `
  main.py
```

ビルドが成功すると `encode-lab/dist/EncodeLab/` フォルダが生成されます。

---

## ffmpeg / ffprobe の配置

ビルド後、以下の構成で ffmpeg バイナリを配置します。

```
dist/
  EncodeLab/
    EncodeLab.exe          ← メイン実行ファイル
    ffmpeg/
      ffmpeg.exe           ← ここに配置
      ffprobe.exe          ← ここに配置
    (PySide6 DLL 群など)
```

### バイナリ検索の優先順位

`main.py` の起動時に以下の順序で ffmpeg を探します。

1. `<exe と同じフォルダ>/ffmpeg/ffmpeg.exe`（同梱バイナリ）
2. システムの PATH 上の `ffmpeg`（インストール済み ffmpeg へのフォールバック）

`ffmpeg/` フォルダが存在する場合はその中を優先的に使うため、
システムへの ffmpeg インストールは不要です。

---

## 出力される dist 構成

```
dist/
  EncodeLab/
    EncodeLab.exe
    ffmpeg/              ← 手動で配置
    _internal/           ← PySide6 DLL・Qt プラグイン（PyInstaller が自動生成）
    ...
```

> **注意**: `_internal/` フォルダ名は PyInstaller のバージョンによって異なる場合があります。
> `dist/EncodeLab/` フォルダ全体を丸ごと配布してください。

---

## ビルド成果物の確認

```powershell
# exe が起動するか確認
.\dist\EncodeLab\EncodeLab.exe
```

起動後、以下を確認してください。

- [ ] GUI ウィンドウが表示される
- [ ] ステータスバーに ffmpeg / ffprobe のパスが表示される（ffmpeg 配置済みの場合）
- [ ] ffmpeg 未配置の場合、ログに「not found on PATH」警告が出る
- [ ] 動画ファイルをドロップするとファイルリストに追加される
- [ ] ffprobe による動画情報（時間・解像度・コーデック）が取得される
- [ ] 変換を実行して出力ファイルが生成される
- [ ] 元ファイルが上書きされない（出力ファイル名に `_converted` が付く）

---

## v1 で行ったコード変更

| ファイル | 変更内容 | 理由 |
|---|---|---|
| `main.py` | `_prepend_bundled_ffmpeg()` 追加 | 同梱 ffmpeg を PATH に追加して既存の `shutil.which` / subprocess 呼び出しをそのまま使えるようにする |
| `logic/converter.py` | `subprocess.CREATE_NO_WINDOW` フラグ追加 | `--windowed` ビルドで ffmpeg 実行時に黒い CMD ウィンドウが点滅するのを防ぐ |
| `logic/ffprobe_reader.py` | `subprocess.CREATE_NO_WINDOW` フラグ追加 | 同上（ffprobe 呼び出し） |
| `logic/environment.py` | `subprocess.CREATE_NO_WINDOW` フラグ追加 | 同上（ffmpeg -encoders 呼び出し） |
| `EncodeLab.spec` | 新規作成 | 再現性のあるビルドのための PyInstaller スペックファイル |

既存のロジック・UI コードの書き換えはありません。

---

## 既知の制限（v1）

1. **コードサイニング未対応**: 配布 exe は署名なし。Windows Defender が未知のファイルとして警告を出す場合があります。
2. **ffmpeg バイナリ同梱なし**: ffmpeg / ffprobe は配布者が別途用意して配置する必要があります（ライセンス上の理由）。
3. **アイコン未設定**: exe にアイコンが設定されていません（`EncodeLab.spec` の `icon=None` を変更することで設定可能）。
4. **UPX 圧縮**: デフォルトで UPX が有効です。UPX が未インストールの場合はエラーになるため、その場合は `upx=False` に変更してください。

---

## 次回以降の改善案

- アイコン（`.ico` ファイル）の追加
- コードサイニング対応
- `--onefile` ビルドの検討（単一 exe への変換；起動が若干遅くなる）
- ffmpeg バイナリのダウンロード自動化スクリプト
- インストーラー（NSIS / Inno Setup）の作成
- GitHub Actions による CI ビルドの自動化
