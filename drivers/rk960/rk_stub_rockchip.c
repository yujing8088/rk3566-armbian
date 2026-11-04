// SPDX-License-Identifier: GPL-2.0
/*
 * Stubs for the Rockchip BSP wifi power-control helpers declared in
 * include/linux/rfkill-wlan.h (BSP header is not in mainline kernels).
 *
 * On rk3566-evb2 the RK960 module is powered by a fixed regulator enabled
 * from the device tree and hangs off an always-on SDIO host, so power and
 * card-detect requests are no-ops.
 *
 * The RK960 firmware signals completion of its startup handshake (and every
 * later packet) by asserting the OOB host-wake GPIO (GPIO2_B2 on this board,
 * described by the "wlan-platdata" node in the board DTS).  In-band SDIO
 * interrupts are never asserted by this firmware: with irq = 0 the driver
 * times out with "Timeout waiting on device startup" while the OOB line sits
 * high.  So parse the DTS node and return the mapped IRQ here.
 *
 * MAC provisioning comes from the chip efuse inside the firmware, with a
 * random address as final fallback, so rockchip_wifi_mac_addr() reports
 * "not available".
 */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_gpio.h>
#include <linux/gpio.h>

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
	struct device_node *np;
	enum of_gpio_flags flags;
	int gpio, irq;

	np = of_find_compatible_node(NULL, NULL, "wlan-platdata");
	if (!np)
		return 0;

	gpio = of_get_named_gpio_flags(np, "WIFI,host_wake_irq", 0, &flags);
	of_node_put(np);
	if (!gpio_is_valid(gpio)) {
		pr_info("rk960 stub: no valid WIFI,host_wake_irq gpio\n");
		return 0;
	}

	irq = gpio_to_irq(gpio);
	pr_info("rk960 stub: oob gpio %d -> irq %d (flags 0x%x)\n",
		gpio, irq, flags);
	return irq > 0 ? irq : 0;
}
EXPORT_SYMBOL_GPL(rockchip_wifi_get_oob_irq);

int rockchip_wifi_mac_addr(unsigned char *buf)
{
	return -1;
}
EXPORT_SYMBOL_GPL(rockchip_wifi_mac_addr);

MODULE_LICENSE("GPL");
