# fnOS (ophub) 内核模块补充包 — RK3566 EVB2 LP4X V10

> 目标：让 **fnnas-rk3566-evb2-ophub-k6.18.18.img** 点亮板载 MIPI-DSI 屏
> （800×1280）并支持 GSLX680 触摸，**不换内核、不动镜像结构**。

## 原理

fnOS 的 ophub 6.18.18-trim 内核显示子系统齐全（`DRM_ROCKCHIP=m`、
`DW_MIPI_DSI=m`、`BACKLIGHT_PWM=m`、fbcon 开），唯独缺：

| 缺什么 | 补什么 | 来源 |
|---|---|---|
| 通用 DSI 面板驱动（认识 `panel-dsi-simple` compatible） | `panel-simple-dsi.ko` | Armbian `general-add-panel-simple-dsi.patch`（我们 Armbian 固件点亮屏幕用的同一版） |
| Silead/GSLX680 触摸驱动 | `silead.ko` | Armbian `1000-input-silead-*` 补丁 |

ophub 内核 `CONFIG_MODVERSIONS=n`、`CONFIG_MODULE_SIG=n`，所以只要
**vermagic 一致**（`6.18.18-trim SMP preempt mod_unload aarch64`）即可干净加载：
编译时用镜像 `/boot/config-6.18.18-trim`（已提取到本目录）+ `LOCALVERSION=-trim`
还原 release 字符串。

## 构建（GitHub Actions 自动）

推送本目录即触发 `build-fnnas-modules` workflow（也可手动
`workflow_dispatch`），产物 artifact：`fnos-evb2-modules-6.18.18-trim`
含 `panel-simple-dsi.ko`、`silead.ko`、`gsl1680-evb2.fw`。

> **实战记录（2026-11-06，推荐方式：板上原生编译）**
> fnOS 1.2.1000+ 升级后内核为 `6.18.18.c1196-trim`（与 ophub 原版
> `6.18.18-trim` 的 vermagic 不同：无 preempt）。而 fnOS 板上自带
> `/usr/src/linux-headers-6.18.18.c1196-trim`（含 Module.symvers）+
> gcc12 —— 把 `panel-simple-dsi.c` + 补丁版 `silead.c` + Makefile 传上去
> `make -C /usr/src/linux-headers-6.18.18.c1196-trim M=$PWD modules`
> 即可编出精确匹配的 .ko，无需 CI。触摸固件驱动按 DT 取名
> `silead/gslx680_fw.fw`（两份名字都装）。

## 板端安装

```bash
# 1. 下载 artifact 解压，传到 fnOS（fnOS 默认 SSH 端口 9222，用户名 fn）
# 2. root 执行：
bash install-on-fnos.sh
# 3. 重启
```

前置条件：fnOS 的 BOOT 分区已按守护方案放好我们的 DTB
（`rk3566-evb2-lp4x-v10.dtb`，面板节点 compatible=`panel-dsi-simple`，
正是本驱动匹配的字符串），`armbianEnv.txt` 的 `fdtfile` 指向它。

## 验证

```bash
dmesg | grep -Ei 'panel|dsi|silead'    # 应看到 panel-simple-dsi probe 成功
ls /dev/fb0                            # framebuffer 存在
# 触摸：
cat /proc/bus/input/devices | grep -A4 silead
```

## 注意

- fnOS 升级后 `/lib/modules` 可能被重置，重跑一遍 `install-on-fnos.sh` 即可
- 屏幕上显示的是 fnOS 文字控制台（fnOS 无桌面环境）
- `silead.c` 由 CI 从 mainline 6.18.18 源码打补丁后取出，勿手工改动本目录外的版本
