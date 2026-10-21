# practising piano easily

MIDI キーボードと楽譜を使って、音名・コード・読譜を自分のペースで練習する Windows デスクトップアプリです。

[English](README.en.md) · [简体中文](README.zh-CN.md)

## 主な機能

- 24 の入門レッスン、12 の練習曲、10 章のコード解説と確認問題
- 目標を先に確認し、不足する音を足したり、間違いを修正したりできるコード練習
- 五線譜と落下ノーツの同期表示、4 小節単位の練習、区間反復、デモ再生
- 両手・右手・左手の切替、音名表示、楽譜の拡大率と段あたり小節数の調整
- ローカル MIDI と任意の PDF の読み込み、利用条件に従ったオンライン楽譜の検索
- 聴音、和声分析、声部進行の比較、コード進行の MIDI 書き出し
- SQLite による練習記録と設定の保存、日本語・简体中文・English の界面切替

MIDI キーボードがなくても、画面の鍵盤をクリックして基本動作を試せます。

## 動作環境

Windows 10 / 11 x64。ソースから実行する場合は Python 3.11 以降が必要です。現在の検証環境は Python 3.13 と PySide6 6.8.3 です。

## ソースから起動

リポジトリのルートで実行します。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m practising_piano_easily.app
```

セットアップ後は `start.bat` からも起動できます。言語は右上の選択欄で変更します。ソース版の初期言語は简体中文、Windows 配布版の新規プロファイルは日本語です。保存済みの言語設定を優先します。

MIDI 鍵盤はデータ転送に対応する USB ケーブルで接続し、「MIDI モニター」で入力デバイスを選択します。通常の練習音は鍵盤側の音源を使用し、アプリ内の試聴・デモには簡易合成音を使用します。

## Windows 配布版を作成

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -X utf8 packaging/build_portfolio.py
```

出力は `exports/portfolio/practising-piano-easily-windows.zip` です。ZIP をすべて展開して `practising-piano-easily.exe` を実行します。Python の追加インストールは不要です。`_internal` フォルダーを EXE と一緒に保持してください。

配布版は未署名です。実行先のセキュリティポリシーに従ってください。

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

テストは音楽理論、MIDI 状態、練習判定、時間軸、保存、言語切替などを扱います。Windows EXE の起動チェックは [検証手順](packaging/VERIFICATION.md)を参照してください。

## データとプライバシー

- ソース版：リポジトリ内の `data/`
- Windows 配布版：`%LOCALAPPDATA%/practising-piano-easily/`
- 既存のインストールでは、以前の保存場所をそのまま利用する場合があります。

練習記録・設定・読み込んだ曲はローカルに保存します。オンライン検索・ダウンロードは利用者の操作時に行います。Git と配布 ZIP には個人 DB、読み込んだ曲、音源、認証情報を含めません。

## 現在の制約

音高とオクターブの練習が中心で、リズム・保持時間・運指・表現の採点は行いません。MIDI からの記譜と左右の振り分けは原譜の完全な復元ではありません。PDF 単体の音符認識は行いません。コード・調の分析は候補であり、確率や唯一の正解を示すものではありません。

外部楽譜サイトのライセンス・認証・提供状況に従って利用してください。取得した第三者楽譜や音源はリポジトリに含まれていません。

## プロジェクト構成

```text
practising_piano_easily/
  core/          音名・音程・コード・和声のモデル
  trainers/      問題生成・練習判定・時間軸
  midi/          リアルタイム MIDI 入力
  audio/         合成音とデモ再生
  analysis/      MIDI 解析・楽譜検索と読み込み
  composition/   コード進行と MIDI 出力
  progress/      学習記録とレポート
  ui/            Qt の画面・表示用翻訳
  content/       英語・中国語・日本語の教材
tests/           自動テスト
docs/            設計と判定仕様
packaging/       Windows ビルド・配布用資料・第三者ライセンス
```

[設計](docs/ARCHITECTURE.md) · [音楽理論モデル](docs/MUSIC_THEORY.md) · [練習判定](docs/TRAINING_MODEL.md) · [対応範囲](docs/ROADMAP.md) · [第三者ライブラリ](packaging/THIRD_PARTY.md)
