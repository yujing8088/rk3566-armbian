# 进展日志 / CHANGELOG

本文件按日期记录这块 **RK3566 EVB2 LP4X V10** 移植过程中每一轮做了什么、结论是什么、踩过哪些坑。

- 硬件识别与引脚分析 → [`analysis/hardware-report.md`](analysis/hardware-report.md)
- 构建 / 刷机 / 救砖 → [`README.md`](README.md)
- 每个镜像的产物与校验值 → 见下方对应日期的「镜像」条目

> 版本号规则：每轮修复都触发一次 GitHub Actions 构建，产物在 Run 的 Artifacts 里，
> `sha256` 由 workflow 在注入完成后重算（注入会改动镜像内容，Armbian 原始 `.sha` 已失效）。

---

## 2026-11-06 — XFCE 桌面版实机调通：触摸标定 + 横屏跟随旋转

### 镜像

`Armbian-unofficial_26.11.0-trunk_Rk3566-evb2-lp4x-v10_jammy_current_6.18.60_xfce_desktop.img`
（CI run `42075514129`，XFCE/mid 档，sha256 `d1e1ecef34a9d000fde221fff3f97e5c0993f428c2643f091a97ca5664ee2c25`）。
首次桌面构建（run `42053843414`）失败的原因与修复见上一节 `patch-jammy-desktop.sh`。

### 实机验证结论（板 192.168.10.252，XFCE + lightdm + autologin admin）

**首启必先落字符界面是设计行为**：首启向导（root/armbian 登录 → 改密 →
建用户）完成后 `armbian-firstlogin` 自动拉起 lightdm 进桌面。

### 触摸标定（silead_ts / GSL1680）

1. **装向与标定**：触摸传感器与面板装向差 90°，且实际有效区域
   X 10–1017 / Y 9–632 ≠ 内核标称 0–1279 / 0–799。用「四角触摸取极值」法
   （与点击顺序无关）实测范围，得出含轴交换+缩放+偏移的 udev 基础标定：
   `ENV{LIBINPUT_CALIBRATION_MATRIX}="0 1.282504 -0.014446 1.270109 0 -0.009930"`
   （`/etc/udev/rules.d/99-touch-cal.rules`，限定 `ATTRS{name}=="silead_ts"`）。
2. **跟随旋转**：X11 下 libinput 不自动跟随显示旋转。守护
   `/usr/local/bin/touch-follow-rotate`（systemd `touch-follow.service`，
   WantedBy=graphical.target）每 2 秒解析 `xrandr` 旋转态并用
   `xinput set-prop "Coordinate Transformation Matrix"` 覆盖。
   **坑**：因 udev 基础标定已含 90° 轴交换，守护表里的 left/right 必须
   与教科书表**对调**（否则叠加出 180° 颠倒），实测定案：
   - `left` → `0 -1 1 1 0 0 0 0 1`
   - `right` → `0 1 0 -1 0 1 0 0 1`
   - `inverted` → `-1 0 1 0 -1 1 0 0 1`
   - `normal` → identity（纯靠 udev 基础标定）
3. **踩坑**：SSH 里 `pkill -f <pattern>` 会匹配到自己的 bash -c 命令行并自杀，
   后续命令静默不执行（表现为守护「启动成功」实际没跑）——用 `[t]ouch-follow`
   正则技巧或直接交给 systemd；`su admin -c` 在 SSH 非交互通道不稳定，
   守护以 root 跑、读 `/home/admin/.Xauthority`。

### 自动登录

`/etc/lightdm/lightdm.conf.d/22-armbian-autologin.conf`：
`autologin-user=admin` + `user-session=xfce`。

---

## 2026-11-05（晚）— 产出 Ubuntu 22.04 LTS 镜像

### 做法：板级支持零改动，只放开发行版选项

`config/distributions/jammy` 在 Armbian 里是社区支持等级（community supported），
但 `apt.armbian.com` 的 `jammy/main`、`jammy-desktop`、`jammy-utils` 组件齐全，
`build.sh` 本来就支持 `RELEASE` 透传，所以只需要：

1. `.github/workflows/build-armbian.yml` 的 `release` 选项加 `jammy`
2. 触发时 `release=jammy&branch=current&minimal=true`

其余全部复用：自研 DTB 安装、silead 触摸固件、RK960/AIC8800 驱动注入、
`rk_hciattach` + `rk960-bt.service`、bluez 兜底安装 —— 这些都是 release 无关的。

### 产物

`Armbian-unofficial_26.11.0-trunk_Rk3566-evb2-lp4x-v10_jammy_current_6.18.60_minimal.img`
1,929,379,840 字节（1.80 GiB），内核 6.18.60 current，
`sha256 c3a36b97a5507566af620674c456aa414b47df7cdf6b8a6c0ba2349e3c5f212f`，
CI run `42028287746`（耗时 1 h 55 min，与 bookworm 一致）。

镜像内已核实字符串命中：`Ubuntu 22.04`、`bluetooth.service`、`bluetoothctl`、
`hciconfig`（jammy 里在 `/bin/hciconfig`）、`rk960-bt.service`、`rk_hciattach`、
`rk960_wifi.bin`、`gslx680_fw.fw`、`panel-simple-dsi`、`rk3566-evb2-lp4x-v10.dtb`、`aic8800_fdrv.ko`。

### 踩坑：注入后重算 sha256 的 `cd` 路径错了，artifact 里带的是旧哈希

workflow 里「注入驱动」这一步的 cwd 是**仓库根目录**，但收尾写的是：

```bash
cd output/images && ... && sha256sum -b "$IMG" | ... > "${IMG}.sha"
```

`cd output/images` 必然失败（真实路径是 `build/output/images`）。而 `set -e`
对 `&&` 链里非末尾命令的失败**不会退出**，于是整条链被静默跳过，
artifact 里打包的是 Armbian 构建阶段（注入之前）生成的 `.sha`。
本次实测：打包值 `444893e0…`，真实值 `c3a36b97…`（本地 `sha256sum` 与
Python `hashlib` 双向确认；拿 bookworm 镜像对照过，本地算出的值与已发布的
`bf8cef89…` 一致，排除本地工具问题）。

修法（commit 见下）：

- 路径改为 `build/output/images/`，用子 shell `( cd ... )` 只影响本次计算
- 算完立刻**自校验**：`sha256sum -b "$IMG"` 与刚写入的 `.sha` 比对，不一致直接 `exit 1`

> ⚠️ 已交付的 jammy 镜像请以 `c3a36b97…` 为准；
> 同目录下的 `.sha256` 由本地按真实内容重算覆盖，zip 内的旧 `.sha` 已删除。

---

## 2026-11-05 — 首版镜像实机验证：BT 根因定案 + WiFi「卡死」是假象

### 蓝牙：ROM 播报波特率是 115200，不是 1500000

串口直抓证据（B7 = `GPIO2_B7`/gpio79 复位释放后）：

```
115200   : 52 4b 55 41 52 54 52 4b ...  → "RKUARTRKUARTRKU..."
1500000  : 00 00 00 00 / f0 00 ...       → 帧错误，全 0
```

之前一直按 1.5M 喂 `rk_hciattach`，协议必然失败，并把芯片打进 break 态（只能断电恢复）。
这就是之前表现为「开机时序随机、有时能起来、多数时候起不来」的真正原因。

正确流程（`tools/rk960-bt-init.sh`）：

1. `gpio79` 拉低 400 ms（把 BT 核按在复位里），串口配 115200 并排空 in-flight 播报
2. 放开 `gpio79` → ROM 开始播报 `RKUART`
3. `rk_hciattach -n -s 115200 /dev/ttyS1 rockchip 3000000 flow nosleep <MAC>`
   —— 46 KB 固件约 4 s 下完，随后 `fc84` 切 3 M + HCI Reset
4. 判定 `hci0` 就绪 → `modprobe rk960`（**BT 固件必须先于 WiFi 固件加载**，否则 BT 核不再进 ROM）
5. `wait` 保持 hciattach 常驻（脚本退出会被 systemd 连同 cgroup 回收，`hci0` 随之消失）

顺带修了 `rk_hciattach` 的一个死锁：`UartReadn` 阻塞读满 12 字节，部分 ROM 的 ACK 更短 →
改成 300 ms `select` 窗口、读到 `ACK ` 标签即继续。

### 镜像缺 bluez 导致 WiFi 晚 4.5 分钟出现

首版镜像（`c6d61ae`）刷机后实测：**minimal 镜像不带 bluez**，`hciconfig` / `bluetoothctl` /
`bluetoothd` 全都没有。而 `rk960-bt-init.sh` 当时用 `hciconfig` 判断固件是否下载完成 →
判定恒假 → 白等 3×90 s 才执行兜底的 `modprobe rk960`。

修法：

- 板级配置加 `PACKAGE_LIST_BOARD="bluez bluez-tools rfkill"`
- CI 注入后 `chroot` 校验 `hciconfig`，缺失则补装 bluez，并显式建
  `bluetooth.service` 的 wants 链接（chroot 里 apt 不会 enable 服务）
- 脚本主判据改为 `/sys/class/bluetooth/hci0` 是否存在（hciattach 在固件下载 + HCI Reset
  之后才向内核注册该设备），有 `hciconfig` 时再升级确认为 `UP RUNNING`

### 重要更正：WiFi 的 `ip link set wlan0 up` 并不卡死

前一版结论说 `up` 会锁死 rtnl、SSH 登不上、只能断电 —— **那是错的**。干净冷启动的新镜像下：

| 测试 | 结果 |
|---|---|
| `ip link set wlan0 up` | 立即返回 |
| `iw dev wlan0 set type managed; iw dev wlan0 scan` | 1 秒内 3~4 个 BSS |
| `iw dev wlan0 set type __ap` | 正常切到 `type AP` |
| 系统稳定性 | 全程 SSH 在线，无 rtnl 死锁 |

之前的卡死是在板端反复 `modprobe` + 手编 dtb（B7 下拉进 uart1 pinctrl、禁 uart1 做
gpiomon 监听）等实验把 SDIO/芯片状态搞坏后的现象，不是驱动固有 bug。

### 验证结果

- 开机 **4 秒** `hci0` UP RUNNING（attempt 1 一次成功，连续多次冷启动一致）
- `rk960` 加载 → `wlan0` 出现 → WiFi 扫描 3~4 个 BSS、BLE 扫描 2~3 个设备
- `hi846` chip id `08 46`、4 lane；rkcif 注册 `/dev/video0/1/3/4`，拓扑完整

**提交**：`28c2d94`（推送后远端 `398e053`）· **CI**：run `41970705615`

### 第二版镜像（bluez 内置）刷机后全绿

刷入 `bf8cef89…` 后冷启动 34 秒时抓的状态：

| 项 | 结果 |
|---|---|
| bluez | ✅ 内置 `bluez 5.66-1+deb12u2`，`hciconfig` / `bluetoothctl` 开箱可用 |
| `bluetooth.service` | ✅ active（CI 补的 wants 链接生效） |
| `rk960-bt.service` | ✅ active，`attempt 1` → 开机 **4 s** `hci0 UP RUNNING` |
| hci0 | `UP RUNNING`，ACL MTU 1021:8 / SCO 255:4，errors 0 |
| `rk960` 驱动 | ✅ 已加载，`wlan0` 开机几十秒内出现（上一版要 4.5 分钟的问题消失） |
| WiFi | `ip link up` 立即返回，`iw scan` 1 秒 **4 个 BSS** |
| BLE | 28 s 扫到 **4 个设备**（含 `midea`），与 WiFi 共存正常 |

dmesg 里仅有已知无害项：panfrost 无 mali regulator（GPU 不用）、`aic8800_bsp` 上电失败
（不用它）、`uart fe650000` DMA 失败（走 PIO）、`rk960_sdd.txt` 缺文件（不影响）。

**镜像**：`Armbian-unofficial_26.11.0-trunk_Rk3566-evb2-lp4x-v10_bookworm_current_6.18.60_minimal.img`
`sha256 bf8cef896355963c030494a0538093b8c42b0130cb80a7423015220953fda601`（1,904,214,016 字节）
核对方式：本地 `sha256sum` 与 CI 的 `.sha256` 一致；另在 `.img` 里直接搜到
`bluetooth.service` / `bluetoothctl` / `bluez-tools` / `bt_ready` 字符串，确认两个修复都真的进了镜像。

> 踩坑留档：用 `timeout N cmd | grep …` 抓扫描结果，管道块缓冲会在 `timeout` 发 SIGTERM 时
> 把输出丢掉，导致误判「扫不到设备」。验证这类命令要重定向到文件再读；
> 另外 `bluetoothctl` 需 ≥25 s 才稳定出结果，紧跟 WiFi 扫描的 16 s 窗口可能为 0。

---

## 2026-11-04 — 摄像头链路 / 外接四键 / RK960 WiFi+BT 驱动移植

### 摄像头：三级链路 + 从 v6.19 回移 rkcif/rkcsi

RK3568 的 MIPI 采集是三段式，缺一段都不出节点：

```
HI846 → csi_dphy(fe870000, inno-csidphy) → rkcsi(fdfb0000, CSI-2 协议桥，未进主线)
      → vicap(fdfe0000, rkcif，v6.19 才进主线) → /dev/video0
```

- `userpatches/kernel/archive/rockchip64-6.18/1001-media-rockchip-backport-rkcif-rkcsi-from-v6.19.patch`
  （约 12 万字节：rkcif 12 文件取自 v6.19，`rkcsi.c` 742 行取自 v14 系列）
- 内核配置加 `V4L_PLATFORM_DRIVERS=y`、`VIDEO_ROCKCHIP_CIF=m`、`VIDEO_ROCKCHIP_CSI=m`
- DTS 接线：`hi846_out(4lane,bus-type=4) → csi_in → csi_out → vicap_mipi_input`
- `hi846` 的 `xvclk` 显式给 24 MHz：`CLK_CIF_OUT` 的父时钟无法整数分出 25 MHz
  （1188/47=25.28），主线驱动只 warn 不报错；本板设计本就是 24 MHz

**当前状态**：拓扑完整、sensor 识别正常、`/dev/media0` + `/dev/v4l-subdev0` 就绪，
但 `VIDIOC_STREAMON` 仍返回 `-EINVAL`（`failed to start pipeline -22`），**尚未出图**。

### 外接按键板：音量键是 SARADC 电阻梯，不是 GPIO

- 电源键 `GPIO0_A3`（低有效，KEY_POWER）；呼叫键 `GPIO4_D1`（低有效，code 87）
- **音量 +/- 是 SARADC 通道 0 的电阻梯**：vol+ 实测 raw≈251，vol- raw≈21，松开 1023
- 厂商阈值（298268 µV / 1750 µV）偏低不触发，改为 **1000000 µV / 300 µV**
- `saradc` 必须给 `vref-supply = <&vcc_1v8>`：主线 `rockchip_saradc` 在哑 regulator 上
  `regulator_get_voltage` 返回 `-EINVAL`，而且**不打任何日志**（「没打印的 -22」）
- 需要 `CONFIG_KEYBOARD_ADC_KEYS=m`（已加入 userpatches 内核配置）

### RK960（WiFi+BT combo）驱动移植

用户指路 `radxa/rkwifibt`（develop 分支）。板上实锤 SDIO `vendor=0x0296 device=0x5349`
= `RK960_DEVICE_ID_D`，与驱动 ID 表完全一致。

- **WiFi**：`drivers/rk960/`（37 文件，cw1200 血统），纯 SDIO ID 匹配，**无需 DTS 改动**；
  固件 `filp_open` 直读 `/lib/firmware`：`rk960_wifi_loader.bin` + `rk960_wifi.bin`
  + `rk960_wifi_rf.bin`（`rk960_sdd.txt` 可选，缺了只 warn）
- 6.18 适配：`create_singlethread_workqueue` → `alloc_ordered_workqueue(WQ_HIGHPRI|WQ_MEM_RECLAIM)`；
  `Makefile` 的 `EXTRA_CFLAGS` → `ccflags-y`（v5.3 起移除，否则 `-DHW_RESET` 等宏会静默丢失）
- **BT**：用户态 `rk_hciattach`（`tools/rk-hciattach`，自包含，不依赖 bluez 库），
  固件三件套从厂商 `super_backup.img`（7-Zip 可直接解 LP 格式）的 `vendor.ext` 提取

**提交**：`c4f6292`、`9677015`、`d7f5b32`

---

## 2026-11-03 — USB3.0 供电定位 / 音频三 bug / 麦克风阵列

### USB 三个口全部可用

- USB2.0/OTG 口（`fcc00000`）：主线默认 otg+extcon，实测一直停在 peripheral，
  改 `&usb_host0_xhci { dr_mode = "host"; }` 后 Logitech 接收器正常枚举
- USB3.0 口（`fd000000`）与 HOST2/HOST3 的 5V：厂商 dtb 写的使能脚 `GPIO0_A6` 在本板悬空，
  真实是 `GPIO3_A2`（HOST 上游主开关，regulator `vcc5v0_usb_host`）+ `GPIO3_A1`
  （USB3.0 口自己的负载开关，`&gpio3` 的 `usb3-vbus-hog`）
- 定位方法：`tools/gpiosweep.py` 对全部 97 个闲置 GPIO 双极性二分扫描 + 万用表实测

### 音频：PCM 正常但完全无声 = 三个 bug 叠加

板载是 `I2S1 → 8 脚 I2S DAC（CS4333 类，需 MCLK 12.288 MHz）→ ANT8110 D 类功放 → 喇叭`，
功放使能 `GPIO1_A6`（`spk-ctl`，高有效）。

1. I2S1 TX 主时钟实际跑 1 GHz —— dtsi 只给 `CLK_I2S1_8CH_TX_SRC` 设 1.188 GHz，而 `clocks`
   引用的是不带 `CLK_SET_RATE_PARENT` 的门控，`clk_set_rate(12288000)` 被静默忽略
   （实测 10 s 音频 61 ms 就播完了）
2. `I2S1_MCLKOUT_TX` 是 deviceless gate，无人 enable → PA2 没有 MCLK 输出
3. `rockchip,digital-loopback` 与主模式冲突，打开 PCM 直接 `-EINVAL`

修法全在 DTS：`assigned-clocks` 显式走 FRAC 分频器给 12.288 MHz；在
`simple-audio-card,codec` 子节点声明 `clocks = <&cru I2S1_MCLKOUT_TX>`（simple-card 会在
启动 PCM 时 `clk_prepare_enable`、停止时关闭）；删掉 loopback；SoC 做主。

验证：PDM 麦克风闭环录到 1 kHz 比噪声底高 100 dB，谐波 −40 dB（THD≈1.5%），音准误差 <1%。

### 麦克风阵列

`&pdm` 三麦 `sdi1/2/3` + `rockchip,path-map = <1 2 3 0>`，声卡 `rockchip,pdm-mic-array`（`hw:1,0`）。
`tools/specscan.py` 可以直接当"声学探头"：判断喇叭是否发声、频率是否正确。

---

## 2026-11-02 — 显示/触摸长跑（v5 → v13 镜像迭代）

这一天的主题是「屏幕有背光但不出图」，一共迭代了 13 个镜像才定稿：

| 现象 | 真根因 |
|---|---|
| 灰屏 | `vp1` endpoint `reg=4`（不是 0） |
| 灰屏 | `dclk_vp1` 卡在 24 MHz（时钟树没走到 FRAC 分频） |
| 花屏（雪花噪声） | `dsi,flags` 缺 `MIPI_DSI_MODE_LPM`，面板 init 命令一直以 HS 模式发出 |
| 逐行乱码 | VOP→DSI 的 DPI 交接配置 |

定稿值：`dsi,flags = 0x603`（含 `MIPI_DSI_MODE_LPM` 与 `VIDEO_BURST`），
dclk 由 `PLL_VPLL` 700 MHz / 10 = 70 MHz。

同时确认了 eMMC 损坏的根因，并定下「**镜像不切片**」的交付方式（v3.37 RKDevTool
配 Loader + 强制按地址写可直接刷 1.9 GB 整镜像）。

**镜像**：v5 ~ v13，对应 CI run `#11` ~ `#18`

---

## 2026-11-01 — 套件建立 + 首次云端构建

- 从 `android/` 目录的 16 个分区备份里挖出三样「硬件说明书」：板级 DTB（`boot_backup.img`
  尾部 header v2，`dtb_size=0x1dc57`）、引导链参数（`MiniLoaderAll.bin` / `uboot` / `trust`）、
  分区布局
- 反推主线 DTS，`dtc` 校验零警告；板卡配置 `BOOT_SCENARIO="spl-blobs"` + 主线 U-Boot `v2025.10`
- 首次云端构建成功（约 10 分钟），产物 1.81 GiB

**镜像**：`Armbian-unofficial_26.11.0-trunk_Rk3566-evb2-lp4x-v10_bookworm_current_6.18.60_minimal.img`
`sha256 5408d23a7fcabb2a317d6d4aa9ce857aac5d9f3d1a4007c411f0b7903696cdf5`

---

## 已知待办

| 项 | 现状 | 下一步 |
|---|---|---|
| 相机 `STREAMON -EINVAL` | 拓扑/sensor 都正常，抓不到帧 | 检查 rkcif 的 crop（当前 `crop:(0,0)/0x0`）与 mplane 格式协商，或对比厂商 BSP 的 rkcif 版本 |
| `hi846` xvclk | 24 MHz，驱动期望 25 MHz（只 warn） | 改 DTS 的 `clock-frequency` 到 25000000 试一次（本板晶振是 24 MHz，可能不可行） |
| `rk960_sdd.txt` | 缺失，加载时只 warn | 从厂商 `vendor.ext` 里找出来一起打进固件目录 |
| WiFi 热点自动化 | hostapd/dnsmasq 未装（minimal 镜像），当前只能连 AP 不能开热点 | 加进 `PACKAGE_LIST_BOARD` + `hostapd.conf` + `dnsmasq.d` + nftables NAT 单元 |
| `wlan0` MAC 随机 | 每次启动都变（如 `ae:d0:94:89:85:56`） | 固定热点 BSSID 或做 DHCP 绑定时需要加 `hwaddress` / `macchanger` 规则 |
| 摄像头 ISP | RK3568 上游无 ISP | 只能出 RAW Bayer，软件上做 debayer（`tools/` 里可加） |
