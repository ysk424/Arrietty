# Arrietty

Arrietty は、Blender 内の世界を SteamVR HMD とサイクルトレーナーで走る GPL-3.0-or-later の Blender Extension です。

## Version 0.2.0

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

VRセッションごとの最初のテンキー入力時に、SteamVRのルーム基準とサイクルトレーナーに座ったHMD正面との角度差を一度だけ校正します。以後の前進方向は`Numpad 4 / 6`で決まる体の向きに固定され、頭を横へ向けても進行方向は変わりません。

### テストデータ

`test_data/arrietty_3m_track.blend` は、Blender MCPポート9876を通して作成した幅3 mの走行確認用トラックです。1 Blender Unit = 1 mのメートル設定で保存しています。

## 実機受入試験

2026-08-24、Blender 5.2.0 LTS、SteamVR、HTC VIVE HMD、AMD Ryzen 9 9950X3D、GeForce RTX 5070 Ti、64 GB メモリの環境で、VR セッションを開始して Blender の初期 Cube が HMD に表示されることを確認し、Version 0.1.0 を合格としました。

## 今回の範囲外

Version 0.2.0 は VR セッション操作とテンキーによる手動位置調整を実装しています。Tracker、トレーナー連動走行、地図、Bluetoothはまだ実装していません。

## 動作対象

- Blender 5.2 LTS
- SteamVR / OpenXR
- HTC VIVE HMD

## ライセンス

GPL-3.0-or-later
