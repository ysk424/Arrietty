# Arrietty — 継続作業の記憶

更新: **2026-09-15 JST / 本日の作業終了**

## 今の到達点

ユーザー確認: **「ちゃんと動いた。ここまでOKです。」**

Blenderの世界を好きな身長で歩く、Windows / Godot / OpenXRアプリへ全面的に作り直した。HMD表示、Xbox操作、坂道の上り下り、音声質問から回答までが動作する状態。ここを次回の基準にする。

- HMD: VIVE Pro、SteamVR/OpenXR。終了前の計測は90 FPS、GPU約0.9 ms。
- コントローラー: XInput Controller。接続順が変わってもXboxを優先する。
- **最後に成功したマイクは `マイク (USB Microphone)`。** ユーザーがYで切り替えている。VIVE Proのマイクを指定していたのは途中の試行。
- 最後の音声診断は `stage=answered`、`recognition=question`、`silent=false`。録音約3.64秒、48 kHz、ピーク約-14.1 dB、RMS約-29.6 dB。実際の入力と回答成功を確認できた。
- 最後に記録した歩行位置の例は `(44.27, 4.43, 26.94)` m。開始位置から前進・上昇できている。
- Arrietty本体とPython音声ワーカーは終了済み。OSのシャットダウンは実行していない。

## 次回の起動

1. SteamVRを起動し、HMDを認識させる。
2. XboxコントローラーとUSBマイクを接続する。
3. PowerShellで次を実行する。

```powershell
cd C:\Users\azoo\git\Arrietty
.\start.ps1 "C:\Users\azoo\git\san-marino-vr\san_marino_ground.blend" -h 1.5 -Microphone "USB Microphone"
```

- マイク選択は起動引数または環境変数 `ARRIETTY_MICROPHONE`、実行中はY。Yで選んだ入力先は次の起動には自動保存されないため、上の明示指定を使う。
- `OPENAI_API_KEY` はこのPCの既存の環境変数を使用する。値は表示・文書化しない。GodotとBlenderには渡さない。
- 起動時に現在の `godot/` をキャッシュへコピーする。ソース編集だけでは、既に動いているアプリには反映されない。
- 起動はカメラまたは `WalkStart` を基準にする。前回の終了地点の自動復元は未実装。
- HMDなしの確認は同じコマンドへ `-Desktop` を付ける。

## 合意した仕様

- `start.ps1 <Blenderファイル> [-h 1.5]`。`-h` は地面から目線までの実寸メートル。
- 小人・巨人に対応。速度、段差の許容高さ、HMDの物理的な移動量と両眼間隔は `h / 1.5` に比例。
- 座位と立位の両方。Viewを1秒長押しすると、現在の頭の向きを正面とし、目線を指定高さへ再調整する。自然なしゃがみは残す。
- 左スティックで前後左右、右スティック左右で30度ずつ旋回。
- Xを押しながら話し、離して送信。Bで中止。Yでマイク切替。
- Whisper → 目線画像を受け取るGPT → GPT TTS。現在は観光案内と質問への回答のみ。GPTによるアプリ内操作は実装しない。
- 身長1.5 mで歩行1.4 m/s、段差25 cm、斜面上限50度。飛行・落下なし。足場の端で止まる。
- RTX 5070 Ti 16 GB / Ryzen 9950X3D。ポリゴン削減、LOD、解像度の自動低下は使わない。
- 片眼60 FPSずつは120枚/秒、両眼1組16.67 ms。実機90 Hzでは両眼1組11.11 ms。報告されるGPU時間はコンポジターを含まない。

## 今日直した問題と、戻してはいけない点

### Xboxが一切動かない

Godotの頭トラッカー名は `head`。`/user/head` で取得すると失敗し、移動処理の前で戻ってしまう。`head` と `default` poseを使い、追跡データと信頼度を確認する。音声とキャンセルは頭追跡待ちでも受け付ける。

Xbox再起動後はXInputの番号が0から1などへ変わり、別の仮想HID `0xbeef/0x046d` が先頭に残った。単純にデバイス0や列挙の先頭を固定しない。`connected_pads()` は名前にXInput / Xboxを含む機器を優先し、毎フレーム再評価する。機器が変わったときは押下状態・旋回状態をリセットし、録音途中なら中止する。

### 坂で一瞬だけ進み、止まる

実際の停止地点は `(48.733875, 3.213962, 34.061604)`。足元は緩い坂で正常だが、表示用スキャンから生成した身体の衝突が、地面から約0.96 mの断片に引っ掛かっていた。カプセルを少し浮かせる方法や段差スイープだけでは解決しなかった。

最終方式はユーザー提案の **水平移動先を決め、その地面の高さへ目線を上下させる** 方法。同じフレーム内で補正する。全身のカプセルを使わず、現在の足元近傍への短いレイで地面を追う。遠く上方から最高面を選ぶ方式へ戻すと、橋や建物の上へ飛ぶので避ける。頭の水平経路と上下補正の経路だけ壁・天井を確認する。しゃがんだ実際の頭位置を使う。

`world_collision.gd` は、既存のStaticBody3Dがあれば衝突用データを優先する。ない場合だけ表示メッシュから衝突を生成する。今回のSan Marinoは16枚の地面コライダーを使い、表示スキャンや表示地形の重複衝突を生成しない。

**現状の制限:** San Marinoの衝突用データには建物の壁・手すりがないため通り抜けられる。この点はユーザーへ説明済み。身体全体の壁接触も再現しない。必要になったら明示的な壁の衝突用データを用意する。

実データの回帰確認: 停止座標から上り2.8 m、下り2.8 mを往復し、標高差約20 cmへ追従。歩行処理は平均約0.018 ms / 0.009 msだった。これは局所的なヘッドレス計測。

### 音声の定型文と「聞き取れませんでした」

- 先頭の「ご視聴ありがとうございました」だけを認識文と回答文から取り除く。通常の文章や後続の質問は残す。TTS前にも適用。
- その定型文しか認識されなかった場合、無音だった場合、認識結果が空だった場合の表示を区別する。
- 完全なデジタル無音だけAPI送信を止める。微小な音を閾値で一律に捨てない。
- `Default` は意図するマイクとは限らない。最後の成功入力はUSB Microphone。音量メーターと診断で確認する。
- 録音バスの後段にミュートしたモニターバスを置き、入力レベルを計測しつつハウリングを防ぐ。マイクはX録音中だけ動作する。
- WASAPIは入力開始時に機器変更を適用する場合がある。選択中の `device` と実際の `engine_device` を分けて診断する。録音前にengine側がDefaultでも、選択失敗と即断しない。
- TTSのストリーミングWAVには長さ未確定のヘッダーがあり、Godotで読み込みエラーになった。現在は24 kHz / mono / PCM16を受け取り、Pythonで長さ確定済みWAVに包む。戻さない。

## コードの配置

| ファイル | 役割 |
|---|---|
| `start.ps1` | ユーザー用起動引数 |
| `tools/launch.py` | キャッシュ、変換、Godot起動、別スレッドの音声サービス |
| `tools/export_blend.py` | 元のblendを保存せずGLBへ変換、実寸、WalkStart、非表示の衝突形状 |
| `godot/main.gd` | シーン、OpenXR、Xbox入力、HUD、診断 |
| `godot/walker.gd` | 地面追従、身長、正面調整、頭の物理移動 |
| `godot/world_collision.gd` | 用意済み衝突形状の優先と自動生成 |
| `godot/voice.gd` | PTT、マイク選択・計測、目線画像、非同期HTTP、再生 |
| `tools/voice_service.py` | Whisper、画像対応GPT、TTS、キャンセル、音量解析 |

旧Blender拡張の自転車/BLE/OpenVRコードと同梱wheelは廃止。旧実装はGitの履歴にある。LICENSEと既存の `test_data/` は保持。

## ローカル環境と外部データ

| 内容 | 場所・状態 |
|---|---|
| Arrietty | `C:\Users\azoo\git\Arrietty` / `main` / `https://github.com/ysk424/Arrietty.git` |
| Godotソース | `C:\Users\azoo\git\godot` / `ed1daf0bf001b61586d9930840f2f1394092c079` (4.7.2-stable) |
| Godot実行ファイル | `C:\Users\azoo\git\godot\bin\godot.windows.editor.x86_64.exe` |
| Godotビルド手順 | `C:\Users\azoo\git\godot-local-build\README.md`、同フォルダーの `.venv\Scripts\python.exe build.py` |
| Blender実行ファイル | `C:\Users\azoo\git\build_windows_Release_x64_vc17_Release\bin\blender.exe` (5.2.2 LTS) |
| 元データ | `C:\Users\azoo\git\san-marino-vr\san_marino_ground.blend` |
| 地形の作成・出典 | `san-marino-vr\GROUND_README.md` と同フォルダーの `README.md`、`data/`、`tools/` |
| 今回のキャッシュ | `Arrietty\.cache\6cd04fe65cf29dae83ea86ef` |

Godotには `modules/gltf/gltf_document.cpp` の頂点カラー読み込み修正が未コミットのローカル差分としてある。COLOR_0の有無をマテリアル設定より先に判定する修正で、現在の実行ファイルへ反映済み。**不用意に破棄・上書きしない。** Arriettyの `docs/patches/godot-gltf-vertex-colors.patch` にも保存した。Godot本体のリポジトリには今回Commit/Pushしていない。

San Marinoの地面は公開地形データと測定道路を合わせた約300 m四方。表示27メッシュ、716,024三角形。地面衝突16枚。元blendと変換データはArriettyのGitへ含めない。このPushだけでは外部データ・エンジン実行ファイルを別PCへ復元できないが、このPCには保存済み。

## 検証済み

- `python tools/verify.py`: オフライン一式成功。移動34項目、衝突データ優先、音声Python10項目、単位・非表示衝突を含むBlender→Godot変換。
- 最後の再接続修正後にも `godot/tests/xr_input.gd` 16項目と `godot/tests/microphone.gd` 13項目を再実行し成功。
- `godot/tests/street_regression.gd`: 実際の停止地点から上り下りを確認。
- `tools/verify_voice_live.py`: 当日の前半に合成した日本語質問→Whisper→実際の目線画像とGPT→TTS→Godot WAV読み込みを確認。明示的な有料APIテストのため、文書変更だけで再実行する必要はない。
- 最後にユーザーが実機で「ちゃんと動いた」と確認。USBマイクによる実発話の回答成功も診断で確認。

ログは `.cache/locomotion.log`、`xr-input.log`、`microphone-test.log`、`street-regression.log` など。通常実行の録音・画像・会話本文は保存しない。終了時の診断スナップショットは `.cache/end-of-day-2026-09-15.json`、描画計測はキャッシュの `metrics.json`。いずれもGit対象外。

## 次回について

具体的な次の実装はまだ指示されていない。上のコマンドで成功状態を再開できるようにして、ユーザーの続きの指示を受ける。[ROADMAP.md](ROADMAP.md) は未着手の候補と制限の整理。
