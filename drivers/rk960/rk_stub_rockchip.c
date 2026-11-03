// SPDX-License-Identifier: GPL-2.0
/*
 * Stubs for the Rockchip BSP wifi power-control helpers declared in
 * include/linux/rfkill-wlan.h (BSP header is not in mainline kernels).
 *
 * On rk3566-evb2 the RK960 module is powered by a fixed regulator enabled
 * from the device tree and hangs off an always-on SDIO host, so power and
 * card-detect requests are no-ops. There is no OOB IRQ wired up, so the
 * driver runs in polling mode (irq = 0). MAC provisioning comes from the
 * chip efuse inside the firmware, with a random address as final fallback,
 * so rockchip_wifi_mac_addr() reports "not available".
 */
#include <linux/module.h>

int rockchip_wifi_power(int on)
{
	return 0;
}
EXPORT_SYMBOL_GPL(rockchip_wifi_power);

int rockchip_wifi_set_carddetect(int val)
{
	return 0;
}
EXPORT_SYMBOL_GPL(rockchip_wifi_set_carddetect);

int rockchip_wifi_get_oob_irq(void)
{
	return 0;
}
EXPORT_SYMBOL_GPL(rockchip_wifi_get_oob_irq);

int rockchip_wifi_mac_addr(unsigned char *buf)
{
	return -1;
}
EXPORT_SYMBOL_GPL(rockchip_wifi_mac_addr);

MODULE_LICENSE("GPL");
