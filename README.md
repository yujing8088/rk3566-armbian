# RK3566 EVB2 LP4X V10 → Armbian 移植套件

> 输入：`android/` 目录下从该板子 eMMC 备份出来的 Android 11 分区镜像（16 个文件）
> 输出：可构建出 Armbian 镜像的完整板级支持包（板卡配置 + 自研 DTB + 刷机/救砖脚本）
>
> **云端构建已完成**（2026-11-01）：
> <https://github.com/yujing8088/rk3566-armbian> ·
> 镜像 `images/Armbian-unofficial_26.11.0-trunk_Rk3566-evb2-lp4x-v10_bookworm_current_6.18.60_minimal.img`
> （1.81 GiB，`sha256 5408d23a7fcabb2a317d6d4aa9ce857aac5d9f3d1a4007c411f0b7903696cdf5`）

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
| WiFi | **RK960 = AIC8800**，SDIO 4bit，`WL_REG_ON`=GPIO2_B1，32K=GPIO2_C6 | ⚠️ 需 out-of-tree 驱动 |
| 蓝牙 | AIC8800 BT，UART1 + 硬件流控，reset=GPIO2_B7，wake=GPIO2_C1/PC0 | ⚠️ 同上 |
| USB | USB2 host×2 + USB3 host0(`fcc00000`) + host1(`fd000000`)；VBUS=GPIO0_A6 / GPIO0_C6 | ✅ |
| 显示 | MIPI-DSI0 800×1280@70MHz 4lane，背光 PWM4，enable=GPIO0_C7，reset=GPIO0_D5 | ⚠️ 需加面板描述 |
| 触摸 | GSLX680（I2C1 0x40） | ❌ 无主线驱动 |
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
├── build.sh                        ← 一键构建（Linux / Docker）
├── dts/rk3566-evb2-lp4x-v10.dts    ← 自研板级 DTS（主线风格，已编译验证）
├── out/rk3566-evb2-lp4x-v10.dtb    ← 编译产物，可直接用
├── out/ref-rk3566-box-demo.dtb     ← 备用 DTB（同参考设计，用于兜底对比）
├── userpatches/
│   ├── config/boards/rk3566-evb2-lp4x-v10.csc   ← Armbian 板卡配置
│   └── dtb/rk3566-evb2-lp4x-v10.dtb             ← 构建时注入镜像
├── flash/
│   ├── flash-linux.sh              ← rkdeveloptool 整盘刷 eMMC
│   └── flash-windows.md            ← RKDevTool 图形化刷机 + 回滚 Android
├── analysis/
│   ├── board.dtb                   ← 从 boot.img 中提取的原始厂商 DTB
│   ├── board-vendor.dts            ← 上面 DTB 反编译出的可读 DTS（硬件地图）
│   └── hardware-report.md          ← 完整硬件分析报告
└── tools/                          ← 纯 Python 的 FDT 解析/编译工具链（Windows 也能跑）
    ├── fdt.py  pp.py  analyze_fw.py  build-dtb.sh
```

> `tools/` 里是本次为了在 **Windows 上直接分析/编译设备树** 现写的工具（FDT 解析器、
> 极简 DTS 预处理器 + MSYS2 版 dtc）。Linux 上正常用 `dtc` 即可，这套工具留着方便以后改 DTS 后立刻重编。

---

## 3. 构建 Armbian 镜像

### 3.1 本机 Linux（推荐 Ubuntu 22.04 / Debian 12，≥30GB 空闲）

```bash
cd armbian
./build.sh                    # 默认 Debian bookworm + 当前内核分支
./build.sh noble edge         # 指定发行版 / 内核分支
```

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
| 9 | WiFi | `lspci`/`dmesg` | 需要 AIC8800 驱动+firmware，见第 7 节 |

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
| MIPI-DSI 面板 | 默认关闭 | 在 `panel-simple.c` 加一条 800×1280 面板描述（参数已写在 `dts/` 文件末尾注释里），再打开 `&dsi0` |
| WiFi/BT（AIC8800） | 未启用 | 编译 [aic8800 out-of-tree 驱动](https://github.com/radxa-pkg/aic8800)，装 firmware 到 `/lib/firmware/aic8800*`；SDIO 侧 DTS 已就绪 |
| 触摸 GSLX680 | 无驱动 | 上游无主线驱动，需移植厂商 `gslx680` 驱动（可选，服务器用途可忽略） |
| 摄像头（HI846 等） | 未启用 | 需要 ISP/媒体管线配置，非本次目标 |
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
可选 `release`（bookworm / noble / trixie）、`branch`（current / edge）、`minimal`。

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

