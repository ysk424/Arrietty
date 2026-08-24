# Arrietty

Arrietty は、Blender 内の世界を SteamVR HMD とサイクルトレーナーで走る GPL-3.0-or-later の Blender Extension です。

## Version 0.4.0

3D Viewport のサイドバーにある「Arrietty」タブから、Blender の OpenXR VR セッションを開始・終了できます。

1. SteamVR を起動し、使用する HMD を接続します。
2. SteamVR をアクティブな OpenXR ランタイムに設定します。
3. 3D Viewport で `N` キーを押し、「Arrietty」タブを開きます。
4. 「Dive into Secret World」で VR を開始します。
5. 「Back to Real World」で VR を終了します。

SteamVR、OpenXR ランタイム、HMD、または Blender の OpenXR 対応を利用できない場合はエラーを表示します。

### テンキーによる開始位置調整

マウスカーソルを3D Viewport上に置き、テンキーでVRの開始位置と向きを調整できます。VR開始前と実行中のどちらでも操作できます。

- `Numpad 8`: 向いている方向へ前進
- `Numpad 2`: 後退
- `Numpad 4`: 左旋回
- `Numpad 6`: 右旋回

高さは常にZ=1.5 mです。初期値は1回のキー入力につき0.5 m、5°で、Arriettyパネルから変更できます。位置と向きはシーンに保存されます。キーイベントで動作するため、常時ポーリングは行いません。

VR実行中の前進・後退方向は、その瞬間のHMD正面です。Blenderが保持するOpenXR viewer poseのローカル`-Z`軸をXY平面へ投影・正規化して使うため、上や下を向いても高さはZ=1.5 mに固定されます。HMD座標はテンキーイベント時に読み取り、常時ポーリングは行いません。

### CYCPLUS T2で直線走行

今回のコースは幅3 m、長さ100 mの直線です。操舵やカーブ処理は行いません。

1. VRを開始して直線コースの正面を向きます。
2. ペダルを数回踏み、CYCPLUS T2を起こします。
3. `Numpad 0`を押します。
4. T2の最初の有効なFTMS通知を受信すると、スピーカーから開始音が鳴ります。
5. T2が通知する速度をメートルへ積算し、開始時に固定したHMD正面へ直進します。
6. 100 mのコース終端で自動停止し、終了音が鳴ります。

BLE通知はT2からのプッシュ受信です。Bluetooth値のポーリングは行いません。`Numpad 0`を走行中にもう一度押すと中止できます。

### テストデータ

`test_data/arrietty_straight_100m.blend` は、Blender MCPポート9876を通して作成する幅3 m、長さ100 mの直線走行確認用コースです。1 Blender Unit = 1 mのメートル設定です。以前のオーバルトラックも`test_data/arrietty_3m_track.blend`として残しています。

## 実機受入試験

2026-08-24、Blender 5.2.0 LTS、SteamVR、HTC VIVE HMD、AMD Ryzen 9 9950X3D、GeForce RTX 5070 Ti、64 GB メモリの環境で、VR セッションを開始して Blender の初期 Cube が HMD に表示されることを確認し、Version 0.1.0 を合格としました。

## 今回の範囲外

Version 0.4.0 は VR セッション操作、テンキー調整、HMD正面方向への手動移動、CYCPLUS T2による100 m直線走行を実装しています。操舵、カーブ、Tracker、地図、心拍連動はまだ実装していません。

## 動作対象

- Blender 5.2 LTS
- SteamVR / OpenXR
- HTC VIVE HMD

## ライセンス

GPL-3.0-or-later
