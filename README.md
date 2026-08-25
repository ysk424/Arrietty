# Arrietty

Arrietty は、Blender 内の世界を SteamVR HMD とサイクルトレーナーで走る GPL-3.0-or-later の Blender Extension です。

## Version 0.6.3

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

地上モードの高さはZ=1.5 mです。初期値は1回のキー入力につき0.5 m、5°で、Arriettyパネルから変更できます。位置と向きはシーンに保存されます。キーイベントで動作するため、常時ポーリングは行いません。

VR実行中にテンキー8/2で位置調整するときは、その瞬間のHMD正面を使います。T2による走行の初期方向にはパネルの「Start Direction」を使い、HMDの視線は使いません。このため、走行開始時や走行中に周囲を見ても自転車の進路は変わりません。HMD座標はテンキーイベント時だけ読み取り、常時ポーリングは行いません。

Start DirectionはBlenderのXY軸に合わせ、0°が+X、90°が+Y、±180°が−X、−90°が−Yです。

### CYCPLUS T2と右VIVEコントローラで走行

右VIVEコントローラを自転車のステムへ固定し、CYCPLUS T2の速度で前進しながらハンドル操作で曲がれます。Manekkoで右手に割り当てていたコントローラ`LHR-9EFF8645`を使用します。

1. 右コントローラをステムへ固定して電源を入れ、ハンドルを中央にします。
2. VRを開始し、テンキー4/6でパネルの「Start Direction」をコース方向へ合わせます。
3. ペダルを数回踏み、CYCPLUS T2を起こします。
4. ハンドルを中央に保ったまま`Numpad 0`を押します。保存された「Start Direction」が初期進行方向、最初に受信したコントローラ姿勢が操舵角0°の基準になります。
5. T2と右コントローラの両方を受信すると、スピーカーから開始音が鳴ります。
6. T2が通知する速度をメートルへ積算し、コントローラの左右回転で進行方向を変えます。
7. 走行距離や周回数では停止せず、「Back to Real World」でVRから戻るまで走り続けます。

BLE通知はT2からのプッシュ受信です。Bluetooth値のポーリングは行いません。コントローラ姿勢は走行中だけOpenVRから60 Hzで読み、「Back to Real World」で停止します。コントローラの追跡を失った場合は移動を一時停止します。走行中に`Numpad 0`をもう一度押しても停止しません。

Version 0.6.3ではカーブを強めるため、ホイールベース1.05 mのまま実ハンドル角の50%を仮の前輪操舵角として使います。中央デッドゾーンは1.5°、適用操舵角の上限は±15°です。

パネルの「Lap」は停止距離ではなく周回表示に使う距離です。総走行距離と完了周回数は増え続け、距離による上限はありません。

「Back to Real World」時もOpenVRクライアント自体は終了せず、コントローラ姿勢の読み取りだけを止めます。これはBlenderのOpenXRセッションが利用中のSteamVRクライアントを同時に終了してクラッシュすることを防ぐためです。

### 固定ファイル名の走行ログ

走行開始時に、開いている`.blend`と同じフォルダへ`arrietty_ride.csv`を作成します。ファイルは走行ごとに上書きし、日時別ファイルを増やしません。速度、ケイデンス、パワー、距離、周回数、飛行状態、高度、XY位置、進行方向を記録し、「Back to Real World」で最終行を書いて閉じます。

### 速度連動の飛行モード

走行中に`Numpad Enter`を押すと、地上モードと飛行モードを切り替えます。飛行モードの高度はT2から受信した速度で決まり、10 km/hまでは地上、10 km/hを超えた分について1 km/hあたり1 m上昇します。

`高度 = max(0, 速度[km/h] - 10) m`

たとえば15 km/hなら地上から5 m、20 km/hなら10 mです。表示上のHMD位置Zには、この高度に目線の高さ1.5 mを加えます。`Numpad Enter`をもう一度押すか、「Back to Real World」でVRから戻ると地上へ戻ります。

### テストデータ

`test_data/arrietty_flight_world.blend`は約3.2 km × 2.4 km、周回路約2.6 kmの大型テスト世界です。中央湖、山地、集落、チェックポイント、飛行用リングを配置し、開始位置は周回路南端、開始方向は+Xです。

`test_data/arrietty_3m_track.blend`は幅3 m、中心線約143 mの小型オーバルトラック、`test_data/arrietty_straight_100m.blend`は直進確認用です。すべて1 Blender Unit = 1 mです。

## 実機受入試験

2026-08-24、Blender 5.2.0 LTS、SteamVR、HTC VIVE HMD、AMD Ryzen 9 9950X3D、GeForce RTX 5070 Ti、64 GB メモリの環境で、VR セッションを開始して Blender の初期 Cube が HMD に表示されることを確認し、Version 0.1.0 を合格としました。

同日、CYCPLUS T2の速度通知による100 m直進を完走し、Version 0.4.0を合格としました。続いて右VIVEコントローラ`LHR-9EFF8645`をステムへ固定し、暫定操舵値のVersion 0.5.0で幅3 m・約143 mのオーバルトラックを1周完走しました。操舵感の調整は残りますが、「曲がる」「周回する」という受入条件は達成しています。

機器ID、座標変換、暫定パラメータ、操作手順、次回の作業順序は[`docs/PROJECT_MEMORY.md`](docs/PROJECT_MEMORY.md)にまとめています。

## 今後のバージョン

Version 0.7.0では、ステムに固定した右コントローラ付近へ計器盤を表示します。速度、心拍数、時計、ケイデンス、パワー、距離、周回数、高度、地上／飛行状態を対象とし、未接続の心拍数は`-- bpm`と表示します。

Version 0.8.0では、入力した日時と緯度から空を作ります。12時を天頂とするのがArriettyの表示規則です。ここでArriettyを機能完了とし、その後のGoogle由来の世界は別のBlenderプラグイン「Secret World」として開発します。詳細は[`docs/ROADMAP.md`](docs/ROADMAP.md)に記録しています。

## 動作対象

- Blender 5.2 LTS
- SteamVR / OpenXR
- HTC VIVE HMD

## ライセンス

GPL-3.0-or-later
