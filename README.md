# Arrietty

Arrietty は、Blender 内の世界を SteamVR HMD とサイクルトレーナーで走る GPL-3.0-or-later の Blender Extension です。

## Version 0.1.0

3D Viewport のサイドバーにある「Arrietty」タブから、Blender の OpenXR VR セッションを開始・終了できます。

1. SteamVR を起動し、使用する HMD を接続します。
2. SteamVR をアクティブな OpenXR ランタイムに設定します。
3. 3D Viewport で `N` キーを押し、「Arrietty」タブを開きます。
4. 「Dive into Secret World」で VR を開始します。
5. 「Back to Real World」で VR を終了します。

SteamVR、OpenXR ランタイム、HMD、または Blender の OpenXR 対応を利用できない場合はエラーを表示します。

## 今回の範囲外

Version 0.1.0 は VR セッションの開始と終了だけを実装しています。Tracker、走行、地図、Bluetooth は実装していません。

## 動作対象

- Blender 5.2 LTS
- SteamVR / OpenXR
- HTC VIVE HMD

## ライセンス

GPL-3.0-or-later
