# RK3566 EVB2 LP4X V10 硬件分析报告

分析对象：`../android/` 下 16 个分区备份（Android 11，userdebug）
分析工具：`../tools/`（纯 Python FDT 解析器，Windows 可直接跑）

---

## 1. 镜像逐项分析

| 文件 | 尺寸 | 结论 |
|---|---|---|
| `MiniLoaderAll.bin` | 456 KiB | Rockchip loader（DDR init + miniloader），MaskROM 下载用；主线方案下不再需要，但**留着救砖** |
| `uboot_backup.img` | 4 MiB | 厂商 U-Boot；文件头 `d0 0d fe ed` = FIT 镜像 |
| `trust_backup.img` | 4 MiB | ATF/BL31；前 0x30 字节全 0（签名头在后方） |
| `boot_backup.img` | 50 MiB | Android boot v2：kernel 31.1 MiB + ramdisk 822 KiB + second 6.3 MiB + **DTB 121,943 B**，cmdline `console=ttyFIQ0 ... androidboot.hardware=rk30board` |
| `recovery_backup.img` | 100 MiB | 同上内核 + 30.3 MiB recovery ramdisk + dtbo 623 B |
| `vbmeta_backup.img` | 1 MiB | AVB0，`flags=0` |
| `super_backup.img` | 3.04 GiB | Android 动态分区（2 个 metadata slot，block 4096） |
| `misc / metadata / security / backup / cache` | — | 标准 Android 分区，无移植价值 |
| `baseparameter_backup.img` | 1 MiB | `BASP` 屏参（Rockchip 专用，主线不用） |
| `mmcblk2boot0/1` | 4 MiB ×2 | eMMC boot 分区 |

**关键收获**：DTB 在 `boot_backup.img` 偏移 `0x2489800`，长度 `0x1dc57`。
这是整台机器唯一的「硬件说明书」，已提取为 `board.dtb` 并反编译成 `board-vendor.dts`（5100+ 行可读 DTS）。

```
boot.img 布局（page_size=2048, header v2）
0x000000  header(1660B)
0x000800  kernel   31,164,432 B
0x1DB900  ramdisk     822,366 B
0x1E8400  second    6,320,128 B
0x2489800 dtb         121,943 B   ← 就是它
```

---

## 2. 板卡身份

```
model      = "Rockchip RK3566 EVB2 LP4X V10 Board"
compatible = "rockchip,rk3566-evb2-lp4x-v10", "rockchip,rk3566"
```

瑞芯微官方 **EVB2 参考板 LPDDR4X 版**。与 Armbian 已支持的 `rk3566-box-demo`
同源（大量 GPIO 完全一致），因此主线支持度天然较高。

---

## 3. 电源架构（最容易翻车的地方）

**没有 PMIC。** 全板由分离器件供电：

| 电源 | 方式 | 参数 |
|---|---|---|
| `dc_12v` | DC 输入 | 12 V |
| `vcc5v0_sys` / `vcc3v3_sys` | 固定 | 5 V / 3.3 V |
| `vdd_cpu` | **PWM0 调压**（pwm-regulator，反相） | 800–1200 mV，初始 950 mV |
| `vdd_logic` | **PWM1 调压** | 800–1100 mV，初始 950 mV |
| `vcc3v3_sd` | GPIO0_A5 控制 | 3.3 V |
| `vcc5v0_host` | GPIO0_A6 控制 | 5 V |
| `vcc5v0_otg` | GPIO0_C6 控制 | 5 V |

> ⚠️ 若 DTS 里 PWM 稳压配置错（极性/占空比/初始电压），表现为**内核启动早期挂死**，
> 因为 CPU 电压不对。`dts/` 里已按厂商 DTB 的 `pwms = <&pwmX 0 5000 1>`（反相）配置。

---

## 4. 引脚地图（从厂商 DTB 反推，已写入自研 DTS）

| 功能 | GPIO | 备注 |
|---|---|---|
| 以太网 PHY reset | GPIO4_C2 | active low，`snps,reset-delays-us=<0 20000 100000>` |
| WiFi 复位 (WL_REG_ON) | GPIO2_B1 | `mmc-pwrseq-simple`，post-power-on 200 ms |
| WiFi 32K | GPIO2_C6 | func 1（CLK_RTC_32K 输出） |
| WiFi host wake | GPIO2_B2 | SDIO 中断 |
| WiFi 使能(第二脚) | GPIO0_B0 | 与 WL_REG_ON 同组 |
| BT reset | GPIO2_B7 | |
| BT wake / host wake | GPIO2_C1 / GPIO2_C0 | |
| BT UART RTS | GPIO2_B5 | UART1 硬件流控 |
| 电源键 | GPIO0_A3 | active low，KEY_POWER |
| 通话键 | GPIO4_D1 | active low |
| 工作 LED | GPIO0_C3 | heartbeat |
| 电源 LED | GPIO0_B2 | 常亮 |
| 面板 backlight enable | GPIO0_C0 | 与 UART2 复用冲突（厂商也未真正使用） |
| 面板 enable / reset | GPIO0_C7 / GPIO0_D5 | |
| 触摸 INT / RST | GPIO0_D5? / GPIO0_E? | 见 `board-vendor.dts`（GSLX680，厂商私有） |
| TF 卡 CD | GPIO0_A4 | active low |
| 调试串口 | GPIO0_D0/D1 | UART2 **m0** |

---

## 5. 外设明细

**以太网**：`gmac1` RMII 模式，PHY 地址 0，`clock_in_out="input"`（PHY 供 50MHz），
引脚组 `gmac1m0-miim / clkinout / tx-bus2 / rx-bus2 / rx-er` —— 注意是 **100M**，
不是 EVB 常见配置的 RTL8211F 千兆（这块板的 PHY 位号与配置确实是 RMII）。

**存储**：
- eMMC `sdhci@fe310000`：8bit、HS200、`txclk-tapnum=8`、non-removable
- TF 卡 `sdmmc0`：4bit、SDR50、CD=GPIO0_A4 —— **厂商固件里是 `disabled`**（板上有无卡槽需实机确认）
- SDIO WiFi `sdmmc1`：4bit、SDR104、keep-power-in-suspend

**显示**：MIPI-DSI0，800×1280，像素时钟 70 MHz，4 lane，RGB888，
时序 `hfp 52 / hsync 8 / hbp 48 / vfp 16 / vsync 6 / vbp 15`，
初始化序列 `0x11`(sleep out) + `0x29`(display on)，背光 PWM4。
HDMI / eDP 均为 `disabled`。

**WiFi/BT**：`wifi_chip_type = "rk960"` → **AIC8800**（瑞芯微 WiFi6 模组）。
主线内核无此驱动，需要 out-of-tree 的 `aic8800` + firmware；SDIO 侧的 DTS 已配好，
只要驱动装上就能用。

**I2C1（`fe5a0000`）**：GSLX680 触摸(0x40)、HYM8563 RTC(0x51)、摄像头 sensor(0x26)。
**I2C2（`fe5b0000`）**：HI846 摄像头(0x22)。

---

## 6. 主线上缺失 / 风险清单

| 项 | 风险 | 规避 |
|---|---|---|
| PWM 供电 CPU/LOGIC | **高**（配置错会挂死） | 已按厂商 DTB 参数逐值核对；坏了先换 box-demo dtb 验证 |
| `pmu_io_domains` 电压 | 中（IO 电平不对会花屏/掉卡） | 参照同源 box-demo（vccio4/6=1.8V，其余 3.3V） |
| MIPI 面板 | 中（无驱动 → 无显示） | 默认关闭；参数已备好，需加 panel-simple 条目 |
| AIC8800 WiFi | 中（无主线驱动） | 服务器用途可忽略；要 WiFi 就编 out-of-tree 驱动 |
| RMII 以太网 | 中（时钟/延时） | 已按厂商 DTB；若不通先试 `clock_in_out="output"` |
| TF 卡槽是否存在 | 低 | 厂商固件关闭了 `sdmmc0`，本套件已打开（无卡槽也无副作用） |
| eMMC 时钟相位 | 低 | 沿用厂商 `txclk-tapnum=8` |

---

## 7. 复现方法

```bash
# 1. 从 boot.img 提取 DTB（Windows/Linux 均可，纯 Python）
python ../tools/analyze_fw.py

# 2. 反编译成可读 DTS
python ../tools/fdt.py ../analysis/board.dtb dts > board-vendor.dts

# 3. 用自研 DTS 重新编译 DTB
./../tools/build-dtb.sh
```
