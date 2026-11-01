# Windows 刷机 / 回滚（RKDevTool）

工具：**RKDevTool**（瑞芯微官方，免安装；需先装 `DriverAssitant` 驱动）
获取：Rockchip 官方发布包，或任意 RK3566 厂商固件包里附带。

---

## 0. 动手前先备份 GPT（强烈建议，5 秒的事）

eMMC 的分区表**不在你现有备份文件里**（那 16 个 `*_backup.img` 只是分区内容）。
刷 Armbian 会覆盖 GPT，之后想精确恢复 Android 就靠这张表。

进入 MaskROM 后用 `rkdeveloptool`（Windows 版）读出来：

```bat
:: 主 GPT(LBA0-33) + 备份 GPT(末尾 33 扇区)
rkdeveloptool rl 0 0x22 gpt-primary.bin
::- 末尾位置需要知道总容量，RKDevTool 里"高级功能"能看到；或直接整盘镜像再解析
```

也可以在 RKDevTool 的「高级功能 → 读取」里按 `0x00000000 / 0x22` 读一遍保存。

> 没有这张表也能回滚（见第 3 节的兜底方案），但有了它就能**按分区名精确写回**。

---

## 1. 进 MaskROM

1. 断开电源
2. 按住板上 **MASKROM**（或 **RECOVERY**）键；板上没有按键时，用镊子短接 eMMC 的 **CLK 与 GND**
3. USB 线接板子的 **OTG / 下载口**（不是 USB3 host 口）
4. 上电，等 2 秒后松开

RKDevTool 底部应显示「发现一个 MASKROM 设备」。

---

## 2. 刷 Armbian

RKDevTool → **下载镜像** 页：

| 地址 | 文件 |
|---|---|
| `0x00000000` | `Armbian-*-rk3566-evb2-lp4x-v10.img` |

勾选该行 → 点「执行」→ 等待「下载完成」。

说明：Armbian 镜像内部已经有 GPT、idbloader（sector 64）、U-Boot（sector 16384）、
boot 分区和 rootfs，**整盘从 0 写入即可**，不需要 `parameter.txt`、不需要单独下 loader。

刷完断电重启，串口（UART2，1500000 8N1）看启动日志。

---

## 3. 回滚 Android

### 3.1 有 GPT 备份（精确恢复）

1. 用 [restore-android.py](restore-android.py) 解析 `gpt-primary.bin`，自动把各 `*_backup.img`
   按分区名写回对应 LBA：

```bat
python restore-android.py --gpt gpt-primary.bin --dir ..\..\android --dry-run
python restore-android.py --gpt gpt-primary.bin --dir ..\..\android --apply
```

2. 若脚本不可用，RKDevTool「下载镜像」页手工加行，地址填 GPT 里该分区的
   `First LBA × 512`，文件选对应 `*_backup.img`，逐行执行。

### 3.2 没有 GPT 备份（按备份尺寸推算）

Rockchip 的 `parameter.txt` 是**顺序紧排**的（第一个分区固定在 LBA `0x4000`），
所以只要分区顺序对，用你自己的备份文件尺寸就能算出与原厂一致的偏移：

```bat
python restore-android.py --dir ..\..\android --pack --out .
:: 产出 parameter.txt（可用 rkdeveloptool ppt parameter.txt 写分区表）
:: 产出 restore-android.sh（逐分区 rkdeveloptool wl，含精确 LBA）
```

按你现有备份推算出来的结果（已由脚本核对）：

| 分区 | 起始 LBA | 字节偏移 | 大小 |
|---|---|---|---|
| uboot | `0x4000` | `0x00800000` | 4 MiB |
| trust | `0x6000` | `0x00C00000` | 4 MiB |
| misc | `0x8000` | `0x01000000` | 4 MiB |
| vbmeta | `0xA000` | `0x01400000` | 1 MiB |
| boot | `0xA800` | `0x01500000` | 50 MiB |
| recovery | `0x23800` | `0x04700000` | 100 MiB |
| backup | `0x55800` | `0x0AB00000` | 384 MiB |
| security | `0x115800` | `0x22B00000` | 4 MiB |
| metadata | `0x117800` | `0x22F00000` | 16 MiB |
| baseparameter | `0x11F800` | `0x23F00000` | 1 MiB |
| super | `0x120000` | `0x24000000` | 3112 MiB |
| cache | `0x734000` | `0xE6800000` | 384 MiB |

> ⚠️ **一个已知不确定点**：Android 11 通常还有 `dtbo`（4MiB）分区，但你的备份里没有
> `dtbo_backup.img`。如果原厂布局里有它且位置在 `misc` 之后，那么从 `vbmeta` 起所有偏移
> 都要整体后移 `0x2000` 扇区。核实办法：进 MaskROM 后 `rkdeveloptool rl 0 0x22 gpt.bin`
> 读一次 GPT，用 `--gpt gpt.bin` 模式重新生成即可，脚本会自动按分区名对齐。


### 3.3 完全救砖

只要还能进 MaskROM，板子就一定能救（loader 走 USB，不依赖板载任何分区）：

1. RKDevTool「高级功能」→ 下载 `MiniLoaderAll.bin` 到 `0x00000000`，或
   `rkdeveloptool db MiniLoaderAll.bin`
2. 再按 3.1 / 3.2 写回分区
3. 若连 MaskROM 都进不去，短接 eMMC CLK-GND 上电强制进入

---

## 4. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| RKDevTool 不认设备 | 换 USB 口/线（必须是数据线）、重装 DriverAssitant、确认插的是 OTG 口 |
| 写镜像卡在 99% | eMMC 容量小于镜像尺寸；换更小的 Armbian 镜像或先 `gpt` 重建 |
| 刷完无串口输出 | 检查串口线是否 3.3V TTL、TX/RX 是否交叉、波特率 1500000 |
| U-Boot 起来但内核 panic | DTB 问题，换 `rk3566-box-demo.dtb` 试（见 README 第 5 节） |
| 想保留 Android 双系统 | 不支持（Armbian 会覆盖 GPT）；建议用 TF 卡启动 |
