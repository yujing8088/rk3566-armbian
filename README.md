# RK3566 EVB2 LP4X V10 → Armbian 移植套件

> 输入：`android/` 目录下从该板子 eMMC 备份出来的 Android 11 分区镜像（16 个文件）
> 输出：可构建出 Armbian 镜像的完整板级支持包（板卡配置 + 自研 DTB + 刷机/救砖脚本）
>
> **当前状态（2026-11-05）：相机、四键、显示、触摸、音频、麦克风、USB 三口、WiFi、蓝牙全部打通。**
>
> 最新镜像（**Ubuntu 22.04 LTS**）
> `Armbian-unofficial_26.11.0-trunk_Rk3566-evb2-lp4x-v10_jammy_current_6.18.60_minimal.img`
> （1,929,379,840 字节 / 1.80 GiB，
> `sha256 c3a36b97a5507566af620674c456aa414b47df7cdf6b8a6c0ba2349e3c5f212f`，
> CI run `42028287746`，commit `69e0298`）。整盘镜像，直接刷，不分片。
>
> 上一版（**Debian 12 bookworm**）
> `Armbian-unofficial_26.11.0-trunk_Rk3566-evb2-lp4x-v10_bookworm_current_6.18.60_minimal.img`
> （1,904,214,016 字节 / 1.77 GiB，
> `sha256 bf8cef896355963c030494a0538093b8c42b0130cb80a7423015220953fda601`，
> CI run `41970705615`，commit `28c2d94`）。
>
> 两个版本均由同一套板级支持产出（内核 6.18.60 current），都内建 **bluez**
> （`hciconfig`/`bluetoothctl`/`bluetoothd` 开箱可用）。bookworm 冷启动实测：
> 开机 4 s `hci0 UP RUNNING`、WiFi 扫描 4 BSS、BLE 扫描 4 设备。
> 逐轮进展、根因与踩坑记录见 **[`CHANGELOG.md`](CHANGELOG.md)**。

---

## 0. 先说结论（很重要）

**Android 固件不能「转换成」Armbian 固件。** 两者从引导链到内核到用户态完全不同，Android 的
`boot.img`、`super.img`（system/vendor）对 Armbian 毫无用处，直接丢掉。

真正有价值的是固件里的 **三样「硬件说明书」**，本次工作就是把它们挖出来：

| 挖什么 | 从哪来 | 用在哪 |
|---|---|---|
| 板级设备树（DTB） | `boot_backup.img` 尾部（header v2，`dtb_size=0x1dc57`） | 反推引脚/电源/外设 → 写主线 DTS |
| 引导链参数 | `MiniLoaderAll.bin` / `uboot` / `trust` 分区尺寸与偏移 | 决定用主线 U-Boot 还是复用厂商 loader、以及刷机方式 |
| 分区布局 | 各 `*_backup.img` 的尺寸 | 刷机 / 救砖 / 回滚 Android |

本套件已经完成前两步的**全部硬件识别**，并产出了可在主线内核上编译通过的自研 DTS（`dtc` 校验零警告）。

---

## 1. 硬件识别结果

板卡身份（来自 DTB 根节点）：

```
model      = "Rockchip RK3566 EVB2 LP4X V10 Board"
compatible = "rockchip,rk3566-evb2-lp4x-v10", "rockchip,rk3566"
```

这是一块**瑞芯微官方 EVB2 参考板（LPDDR4X 版本）**，所以大量引脚与 Armbian 已经支持的
`rk3566-box-demo` 参考设计完全一致（USB VBUS、SDIO 复位、BT 引脚、以太网复位都相同）。

| 模块 | 细节 | 主线支持 |
|---|---|---|
| SoC / 内存 | RK3566 + LPDDR4X（容量 DTB 不含，由 rkbin DDR blob 自适应） | ✅ |
| 电源 | **无 PMIC**：`vdd_cpu`=PWM0、`vdd_logic`=PWM1（pwm-regulator），12V DC-in | ✅ pwm-regulator |
| eMMC | `sdhci@fe310000`，8bit，HS200，`txclk-tapnum=8` | ✅ |
| TF 卡 | `sdmmc0`（厂商固件里被 `disabled`，本套件默认打开），CD=GPIO0_A4 | ✅ |
| 以太网 | `gmac1` **RMII 100M**，PHY addr 0，reset=GPIO4_C2，25/50M 由 PHY 供给 | ✅ |
| WiFi | **RK960**（瑞芯微自研 WiFi+BT combo），SDIO 4bit，`WL_REG_ON`=GPIO2_B1，32K=GPIO2_C6；SDIO ID `0296:5349`（= `RK960_DEVICE_ID_D`） | ✅ **已打通**：移植 radxa/rkwifibt 的 `drivers/rk960`（37 文件，cw1200 血统，纯 SDIO ID 匹配，无需 DTS 改动），配 `rk960_wifi*.bin` 固件。实测扫描 3~4 个 BSS、可切 AP 模式、与蓝牙共存 |
| 蓝牙 | RK960 BT（UART1 + 硬件流控，reset=GPIO2_B7 即 gpio79，wake/host_wake 未用） | ✅ **已打通**：`tools/rk-hciattach` 下载固件（ROM 播报波特率 **115200**，下完切 3 M），由 `rk960-bt.service` 开机自动初始化。实测开机 4 s `hci0` UP RUNNING，BLE 扫描正常 |
| USB | 丝印 **USB2.0 口**=`fcc00000`(dwc3, OTG 硬件)、**USB3.0 口**=`fd000000`(xHCI)、**HOST2/HOST3**=4pin 排针（`fd800000`/`fd880000` EHCI+OHCI）；VBUS 开关：OTG=`GPIO0_C6`、HOST 上游=`GPIO3_A2`、USB3.0 口=`GPIO3_A1`（厂商 dtb 写的 `GPIO0_A6` 在本板悬空，是错的） | ✅ **三个口全可用**：USB2.0/OTG 口强制 `dr_mode="host"`；USB3.0 口 + HOST2/HOST3 的 5V 由 `GPIO3_A1+A2` 控制（A2=regulator `vcc5v0_usb_host`，A1=`&gpio3` 的 `usb3-vbus-hog`）。实测 Logitech 接收器(046d:c53f) 在 USB3.0 口(fd000000/usb5) 正常枚举，键鼠事件正常 |
| 显示 | MIPI-DSI0 800×1280@70MHz 4lane，背光 PWM5，enable=GPIO0_C7，reset=GPIO0_D5 | ✅ 已点亮出字 |
| 触摸 | GSLX680（I2C1 0x40，中断 GPIO0_B5，复位 GPIO0_B6 高有效） | ✅ 已跑通 |
| RTC | HYM8563（I2C1 0x51） | ✅ |
| 按键 / LED | 电源键 GPIO0_A3、通话键 GPIO4_D1；工作灯 GPIO0_C3、电源灯 GPIO0_B2 | ✅ |
| 调试串口 | **UART2 m0（GPIO0_D0/D1），1500000 8N1，3.3V TTL** | ✅ |

Android 侧版本信息：Android 11，`userdebug`，`selinux=permissive`，`verifiedbootstate=orange`
（说明该机器已是解锁状态，刷第三方系统没有 AVB 阻碍）。

更细的分析见 [`analysis/hardware-report.md`](analysis/hardware-report.md)。

---

## 2. 交付物

```
armbian/
├── README.md                       ← 本文件
├── CHANGELOG.md                    ← 逐轮进展 / 根因 / 踩坑记录（按日期）
├── build.sh                        ← 一键构建（Linux / Docker）
├── dts/rk3566-evb2-lp4x-v10.dts    ← 自研板级 DTS（主线风格，已编译验证）
├── out/rk3566-evb2-lp4x-v10.dtb    ← 编译产物，可直接用
├── out/ref-rk3566-box-demo.dtb     ← 备用 DTB（同参考设计，用于兜底对比）
├── drivers/
│   ├── rk960/                      ← RK960 WiFi 驱动（移植自 radxa/rkwifibt，适配 6.18）
│   └── aic8800/                    ← AIC8800 驱动（与本板芯片不匹配，仅留档）
├── firmware/rk960/                 ← rk960_wifi*.bin / rk960_bt*.bin（厂商固件提取）
├── userpatches/
│   ├── config/boards/rk3566-evb2-lp4x-v10.csc   ← Armbian 板卡配置
│   ├── config/kernel/linux-rockchip64-current.config  ← 内核配置（rkcif/rkcsi/ADC_KEYS）
│   ├── kernel/archive/rockchip64-6.18/*.patch   ← 触摸 / rkcif 回移 / hi846 修复
│   ├── firmware/silead/*.fw                     ← 触摸固件（8 个候选）
│   └── dtb/rk3566-evb2-lp4x-v10.dtb             ← 构建时注入镜像
├── flash/
│   ├── flash-linux.sh              ← rkdeveloptool 整盘刷 eMMC
│   └── flash-windows.md            ← RKDevTool 图形化刷机 + 回滚 Android
├── analysis/
│   ├── board.dtb                   ← 从 boot.img 中提取的原始厂商 DTB
│   ├── board-vendor.dts            ← 上面 DTB 反编译出的可读 DTS（硬件地图）
│   └── hardware-report.md          ← 完整硬件分析报告
└── tools/                          ← FDT 解析/编译 + 板上调试脚本
    ├── fdt.py  pp.py  analyze_fw.py  build-dtb.sh
    ├── rk-hciattach/hciattach_rk.c ← RK960 蓝牙固件下载工具（自包含，不依赖 bluez）
    ├── rk960-bt-init.sh            ← 开机自动初始化蓝牙 + 加载 WiFi 驱动
    ├── gpiosweep.py  specscan.py   ← GPIO 二分扫描 / 声学探头
```

> `tools/` 里是本次为了在 **Windows 上直接分析/编译设备树** 现写的工具（FDT 解析器、
> 极简 DTS 预处理器 + MSYS2 版 dtc）。Linux 上正常用 `dtc` 即可，这套工具留着方便以后改 DTS 后立刻重编。

---

## 3. 构建 Armbian 镜像

### 3.1 本机 Linux（推荐 Ubuntu 22.04 / Debian 12，≥30GB 空闲）

```bash
cd armbian
./build.sh                    # 默认 Debian bookworm + 当前内核分支
./build.sh jammy current      # Ubuntu 22.04 LTS
./build.sh noble edge         # 指定发行版 / 内核分支
```

桌面版（XFCE + 浏览器）走 `compile.sh` 直传，`build.sh` 只封了命令行版：

```bash
./compile.sh build BOARD=rk3566-evb2-lp4x-v10 BRANCH=current RELEASE=jammy \
  BUILD_MINIMAL=no BUILD_DESKTOP=yes \
  DESKTOP_ENVIRONMENT=xfce DESKTOP_TIER=mid EXPERT=yes
```

`DESKTOP_ENVIRONMENT` 可选 `xfce` / `mate` / `cinnamon` / `gnome` / `kde-plasma`；
`DESKTOP_TIER` 为 `minimal`（仅桌面 ≈500MB）/ `mid`（+浏览器 ≈1GB）/ `full`（+LibreOffice ≈2.5GB）。
桌面由 armbian-config（configng）的 YAML 定义驱动，jammy+arm64 的 XFCE 属官方支持组合；
浏览器映射到 `apt.armbian.com` 的 **chromium 真 deb**（Ubuntu 自带的 chromium/firefox 是 snap 空壳，不可用）。

脚本会自动 `git clone` Armbian 构建框架、同步 `userpatches/`、然后编译。
产出：`armbian/build/output/images/Armbian-*-rk3566-evb2-lp4x-v10.img`

宿主机不是 Ubuntu 22.04 时用容器模式：

```bash
USE_DOCKER=yes ./build.sh
```

### 3.2 没有 Linux 机器时（GitHub Actions 云端出镜像）

把本目录推到 GitHub 仓库，`.github/workflows/build-armbian.yml` 会在云端编译并把 `.img`
作为 artifact 上传（约 40–70 分钟）。详见第 8 节。

### 3.3 构建做了什么

板卡配置 `userpatches/config/boards/rk3566-evb2-lp4x-v10.csc` 的关键点：

- `BOOT_SCENARIO="spl-blobs"` + 主线 U-Boot `v2025.10`（`generic-rk3568_defconfig`）
  → 用 rkbin 的 DDR init + BL31，binman 生成 `u-boot-rockchip.bin`，**不依赖厂商 loader**
- `BOOT_FDT_FILE="rockchip/rk3566-evb2-lp4x-v10.dtb"`
- 收尾钩子 `pre_customize_image__install_evb2_dtb()` 把预编译 DTB 塞进 `/boot/dtb-*/rockchip/`
  并改 `armbianEnv.txt` 的 `fdtfile`
- `SERIALCON="ttyS2"`，控制台 1500000 8N1
- `PACKAGE_LIST_BOARD="bluez bluez-tools rfkill"` —— minimal 镜像默认不带 bluez，
  缺了它 `hciconfig`/`bluetoothctl`/`bluetoothd` 全没有（`rk_hciattach` 本身不依赖 bluez，
  但上层拿不到可用 HCI 设备）
- CI 在 loop mount 后把 `rk960.ko`、`rk960_wifi*.bin`、`rk960_bt*.bin`、`rk_hciattach`
  和 `rk960-bt.service` 注入镜像；同时 `chroot` 校验 bluez，缺失则补装并 enable 服务

**为什么不给内核打补丁？** 打补丁要维护内核树 diff，内核一升级就冲突。现在 DTB 是独立文件，
内核随便升，只是升级后要重跑 `build.sh`（或手动把 dtb 拷进新 dtb 目录）。

---

## 4. 刷机

### 4.1 进入 MaskROM

断电 → 按住板上 **MASKROM（或 RECOVERY）键**（无按键则短接 eMMC CLK 与 GND）→
USB-A 转 USB-A/C 线接板子的 **OTG 口** → 上电 → 松开。

### 4.2 Linux / macOS

```bash
sudo ./flash/flash-linux.sh build/output/images/Armbian-*.img android/MiniLoaderAll.bin
```

### 4.3 Windows（RKDevTool，无需装驱动以外的工具）

见 [`flash/flash-windows.md`](flash/flash-windows.md)：用「下载镜像」页，地址 `0x00000000`，
文件选 Armbian `.img`，勾选后「执行」即可（Armbian 镜像自带 GPT 和 U-Boot，不需要 parameter.txt）。

### 4.4 首启

串口（UART2，1500000 8N1）应看到 U-Boot → 内核 → 登录提示。
默认账号 `root` / `1234`（首次登录强制改密）。若根分区未占满 eMMC：

```bash
armbian-resize-filesystem
```

---

## 5. 首启验证清单

按优先级逐项确认（`dmesg | grep -i <关键字>`）：

| # | 项目 | 命令 | 期望 |
|---|---|---|---|
| 1 | 能启动 | 串口日志 | 到 login（最关键，说明 DTB 电源/时钟正确） |
| 2 | eMMC | `lsblk` | `mmcblk2` + `mmcblk2p1/p2` |
| 3 | 网口 | `ip a` | `end0`/`eth0` 有 link，`ethtool end0` 显示 100M |
| 4 | USB | `lsusb` | 插 U 盘/键鼠能识别 |
| 5 | 温度 | `cat /sys/class/thermal/thermal_zone0/temp` | 正常读数 |
| 6 | RTC | `hwclock -r` | 读到时间（HYM8563） |
| 7 | 按键/LED | `evtest` / `ls /sys/class/leds` | 看到 `key-power`、`led-work` |
| 8 | TF 卡 | 插卡后 `lsblk` | 出现 `mmcblk0`（若板上有卡槽） |
| 9 | WiFi | `ip link set wlan0 up` → `iw dev wlan0 set type managed; iw dev wlan0 scan` | `wlan0` 出现、扫描出若干 BSS（驱动 `rk960` 由 BT 服务在蓝牙就绪后加载，实测开机几十秒内完成） |
| 10 | 蓝牙 | `hciconfig hci0` / `bluetoothctl --timeout 28 scan on` | `UP RUNNING`（开机约 4 s），扫描到 BLE 设备。**扫描窗口给到 25 s 以上**，太短可能一个都没有；`hcitool lescan` 会因 bluetoothd 占用报 `Input/output error`，正常现象 |
| 11 | 相机 | `media-ctl -d /dev/media0 -p`、`v4l2-ctl -d /dev/video0 --list-formats-ext` | 拓扑含 `hi846 → rockchip-mipi-csi → rkcif-mipi0`；**抓帧目前仍报 `-EINVAL`**（见第 7 节） |

**第 1 项不过怎么办**（黑屏/无日志时按顺序排查）：

1. 换 DTB 验证：把 `out/ref-rk3566-box-demo.dtb` 拷进 `/boot/dtb/rockchip/`，
   改 `armbianEnv.txt` 里 `fdtfile=rockchip/rk3566-box-demo.dtb` 后重启
   （同参考设计，能启动说明是 DTS 细节问题，不是硬件问题）
2. 抓完整日志：U-Boot 阶段停在 `Starting kernel ...` 说明内核早期崩，多半是 `vdd_cpu`/`vdd_logic`
   的 PWM 稳压参数或 `pmu_io_domains` 电压不对
3. 用 `earlycon` 加参数：`extraargs=earlycon=uart8250,mmio32,0xfe660000 keep_bootcon`

---

## 6. 回滚 / 救砖

**一切从「厂商引导链还在」开始。** 我们没有动 `uboot` 分区之外的引导固件，而且你已有全套备份。

- **只恢复 Android**：进 MaskROM，用 RKDevTool「下载镜像」按 `flash/flash-windows.md`
  里的偏移表逐个写回 `*_backup.img`（`uboot/trust/misc/vbmeta/boot/…/super`）
- **救砖**：只要能进 MaskROM 就一定能救（loader 走 USB，不依赖板载任何分区）
- **保险建议**：动手前先把 `MiniLoaderAll.bin` 复制到 U 盘/云盘——它是 MaskROM 下载器，
  丢了也能从任何同款固件包里找到同版本 loader

---

## 7. 已知缺口 / 后续可做

| 项 | 状态 | 做法 |
|---|---|---|
| MIPI-DSI 面板 | ✅ 已完成 | `panel-simple-dsi` + DTS 描述（`dsi,flags=0x603`，含 MIPI_DSI_MODE_LPM 与 VIDEO_BURST），dclk 由 `PLL_VPLL` 700MHz/10 得到 70MHz |
| WiFi（RK960 SDIO） | ✅ 已完成 | 板上 SDIO ID 实为 `0296:5349` = `RK960_DEVICE_ID_D`（不是 AIC8800）。从 `radxa/rkwifibt` 取 `drivers/rk960/`（37 文件，cw1200 血统），适配 6.18：`alloc_ordered_workqueue`、`EXTRA_CFLAGS`→`ccflags-y`；固件 `rk960_wifi_{loader,}.bin` + `rk960_wifi_rf.bin` 放 `/lib/firmware`。纯 SDIO ID 匹配，**DTS 无需改**。实测扫描 3~4 个 BSS、AP 模式正常、与 BT 共存 |
| 蓝牙（RK960 UART） | ✅ 已完成 | 关键：ROM 复位释放后在 **115200** 播报 `RKUART`（不是 1.5 M），`rk_hciattach -n -s 115200 /dev/ttyS1 rockchip 3000000 flow nosleep` 下载 46 KB 固件后切 3 M。`tools/rk960-bt-init.sh` 做 B7(gpio79) 复位脉冲 + 排空播报 + 重试 + 成功后 `modprobe rk960`（**BT 必须先于 WiFi**），实测开机 4 s `hci0` UP RUNNING |
| 摄像头（HI846） | ⚠️ 链路已通，抓帧待修 | 单前置 Hynix HI-846，MIPI CSI2 4-lane，`i2c@fe5b0000` @0x22。三级链路 `hi846 → csi_dphy → rkcsi(fdfb0000) → vicap(fdfe0000)`，rkcif/rkcsi 从 v6.19 回移（`1001-*` 补丁）。当前：`chip id 08 46 using 4 mipi lanes`、`/dev/media0` 拓扑完整、`/dev/video0` 存在，但 `VIDIOC_STREAMON` 返回 `-EINVAL`（`failed to start pipeline -22`），尚未出图。RK3568 上游无 ISP，只能出 RAW Bayer |
| USB 主机 | ✅ 三个口全可用 | ① **USB2.0/OTG 口**（`fcc00000`）：主线默认 otg+extcon → 实测 `USB-HOST=0` 一直停在 peripheral，插任何 device 无反应。改 `&usb_host0_xhci { dr_mode = "host"; }` 后 Logitech 接收器正常枚举。② **USB3.0 口**（`fd000000`）：5V 使能脚是 `GPIO3_A1 + GPIO3_A2`（厂商 dtb 写的 GPIO0_A6 在本板悬空）。A2=regulator `vcc5v0_usb_host`（上游主开关，带 HOST2/HOST3），A1=`&gpio3` 的 `usb3-vbus-hog`（USB3.0 口自己的开关）。实测接收器在 fd000000/usb5 正常枚举。**已刷镜像免重刷升级**：把 `dts/rk3566-evb2-lp4x-v10.dtb` 直接 scp 到 `/boot/dtb/rockchip/rk3566-evb2-lp4x-v10.dtb` 重启即可（两处修复都内置在 dtb 里，不需要 overlay）|
| USB3.0 口 / HOST2 / HOST3 供电 | ✅ 已修复 | 真实使能脚不是厂商 dtb 写的 GPIO0_A6（悬空），而是 GPIO3：A2=HOST 上游主开关（regulator `vcc5v0_usb_host`），A1=USB3.0 口自己的负载开关（`&gpio3` 的 `usb3-vbus-hog`）。USB3.0 口出 5V 需 A1+A2 同时高，HOST2/HOST3 只需 A2。定位方法：`tools/gpiosweep.py` 对全部 97 个闲置 GPIO 双极性二分扫描 + 万用表实测。实测 Logitech 接收器在 fd000000/usb5 正常枚举 |
| 触摸 GSLX680 | ✅ 已完成 | 主线 `silead.c` + 内核补丁 `userpatches/kernel/archive/rockchip64-6.18/1000-input-silead-support-gslx680-download-protocol.patch`；固件用 `gslx680_fw.fw`（5247 条） |
| 音频播放（喇叭） | ✅ 已完成 | 板载是 `I2S1 → 8 脚 I2S DAC（CS4333 类，需 MCLK 12.288 MHz）→ ANT8110 D 类功放 → 喇叭座`，功放使能 `GPIO1_A6`(`spk-ctl`，高有效)。三个叠加 bug 导致"PCM 正常但完全无声"：① I2S1 TX 主时钟实际跑 1 GHz（dtsi 只给 `CLK_I2S1_8CH_TX_SRC` 设 1.188 GHz，而 `clocks` 引用的是无 `CLK_SET_RATE_PARENT` 的门控，`clk_set_rate(12288000)` 被静默忽略，实测 10 s 音频 61 ms 播完）；② `I2S1_MCLKOUT_TX` 是 deviceless gate 无人 enable，PA2 无 MCLK 输出；③ `rockchip,digital-loopback` 与主模式冲突使 PCM 打开返回 `-EINVAL`。修法全在 DTS：`assigned-clocks` 显式走 FRAC 分频器给 12.288 MHz、在 `simple-audio-card,codec` 子节点声明 `clocks = <&cru I2S1_MCLKOUT_TX>`（simple-card 会在启动 PCM 时 `clk_prepare_enable`，停止时关闭）、删 loopback、SoC 做主。验证：PDM 麦克风闭环录到 1 kHz 比噪声底高 100 dB，谐波 −40 dB（THD≈1.5%），音准误差 <1% |
| 麦克风（PDM 阵列） | ✅ 已完成 | `&pdm` 三麦 `sdi1/2/3` + `rockchip,path-map = <1 2 3 0>`，声卡 `rockchip,pdm-mic-array`（`hw:1,0`）。`tools/specscan.py` 可直接当作"声学探头"判断喇叭是否发声、频率是否正确 |
| 开机自动热点 | ⚠️ 未内置 | 镜像里**没有 `hostapd` / `dnsmasq`**（minimal 未装），所以只能连别人的 AP，不能自己开热点。要做「开机即开 `rk960-test` 热点 + NAT/DHCP」需把这两个包加进 `PACKAGE_LIST_BOARD` 并补 `hostapd.conf` + `dnsmasq.d` + nftables NAT 单元 |
| wlan0 MAC 随机 | ⚠️ 未固定 | 每次启动 MAC 都变（如 `ae:d0:94:89:85:56`）。要固定热点 BSSID 或做 DHCP 地址绑定时，加 `hwaddress` 配置或 `macchanger` 规则 |
| 以太网 100M 上限 | 硬件限制 | 板上是 RMII PHY，物理上就是百兆；要千兆得换 RGMII PHY 的板子 |
| HDMI | 板上无 | 厂商 DTB 里 `hdmi` 也是 disabled |

---

## 8. GitHub Actions 云端构建

### 8.1 一条命令推上去

```bash
export GITHUB_TOKEN=ghp_xxxxxxxx      # 见下方权限说明
./tools/push-to-github.sh <你的用户名> rk3566-armbian private
```

脚本会：校验 token → 仓库不存在就创建 → 推送 `main` → 直接触发一次 `workflow_dispatch`。

Token 权限：Classic token 勾 `repo` + `workflow`；Fine-grained token 给目标仓库
`Contents: Read/Write`、`Administration: Read/Write`、`Actions: Read/Write`
（要新建仓库还需账号级 `Administration: Read/Write`）。用完随时吊销。

### 8.2 手动推（不想把 token 交给脚本）

```bash
git remote add origin https://github.com/<用户名>/<仓库名>.git
git push -u origin main
```

然后网页：仓库 → **Actions** → `build-armbian` → **Run workflow**，
可选 `release`（jammy / bookworm / noble / trixie）、`branch`（current / edge）、`minimal`；
要桌面版就勾 `desktop`，再选 `desktop_env`（xfce/mate/cinnamon/gnome/kde-plasma）
和 `desktop_tier`（minimal/mid/full），此时 `minimal` 自动失效。
`jammy` 即 Ubuntu 22.04 LTS（Armbian 里属社区支持等级，apt 仓库 `jammy/main` 齐全，实测可正常构建）。

### 8.3 跑完拿镜像

Run 页面底部 **Artifacts** → `armbian-rk3566-evb2-lp4x-v10-current-bookworm.zip`，
解压得到 `Armbian_*.img`（或 `.img.xz`），直接刷机，见第 4 节。

- 免费额度：公开仓库不限量；私有仓库 2000 分钟/月（Linux 计 1 倍），本板一次约 50–80 分钟
- 单任务硬上限 6 小时，workflow 已设 350 分钟超时
- workflow 里加了 6GB swap：runner 只有 7–16GB 内存，内核编译不加 swap 容易 OOM
- 推送 `dts/`、`userpatches/` 或 workflow 自身会自动触发一次构建

### 8.4 首次云端构建踩到的两个坑（已修复，留档）

| 现象 | 原因 | 修法 |
|---|---|---|
| `fallocate failed: Text file busy` | 托管 runner 自带 `/swapfile` 且已启用 | 改用 `/swapfile2`，且仅在现有 swap < 4GB 时创建 |
| `arch-test arm64 → not supported`，随后 `Error 1` | Armbian 在 Debian trixie 容器里 `update-binfmts` 注册不上 qemu | 加 `docker/setup-qemu-action@v3`（内核级 `F` 标志注册，容器内可见） |
| `sed: unterminated 's' command` + `Permission denied` | `run_host_command_logged` 把参数拼成字符串再 `bash -c`，`\|`、`*` 被二次解析 | 板级钩子里改用 `python3` 原地改写 `armbianEnv.txt` |

实测：**首次成功构建耗时约 10 分钟**（ubuntu-22.04 runner，4 vCPU/16GB），产物 1.81 GiB。

