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
 * high.  So look the line up through the gpiod consumer API and return the
 * mapped IRQ here.
 *
 * MAC provisioning comes from the chip efuse inside the firmware, with a
 * random address as final fallback, so rockchip_wifi_mac_addr() reports
 * "not available".
 */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_irq.h>
#include <linux/gpio/consumer.h>

/* Kept for the lifetime of the module: the IRQ stays usable after
 * request_threaded_irq() as long as the underlying GPIO is requested. */
static struct gpio_desc *rk960_oob_gpiod;

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
	int irq;

	np = of_find_compatible_node(NULL, NULL, "wlan-platdata");
	if (!np)
		return 0;

	rk960_oob_gpiod = fwnode_gpiod_get_index(of_fwnode_handle(np),
						 "WIFI,host_wake_irq", 0,
						 GPIOD_IN, "rk960-oob");
	of_node_put(np);
	if (IS_ERR(rk960_oob_gpiod)) {
		int err = PTR_ERR(rk960_oob_gpiod);

		rk960_oob_gpiod = NULL;
		pr_info("rk960 stub: no usable WIFI,host_wake_irq gpio (%d)\n",
			err);
		return 0;
	}

	irq = gpiod_to_irq(rk960_oob_gpiod);
	pr_info("rk960 stub: oob host-wake irq %d\n", irq);
	return irq > 0 ? irq : 0;
}
EXPORT_SYMBOL_GPL(rockchip_wifi_get_oob_irq);

int rockchip_wifi_mac_addr(unsigned char *buf)
{
	return -1;
}
EXPORT_SYMBOL_GPL(rockchip_wifi_mac_addr);

static void __exit rk_stub_exit(void)
{
	gpiod_put(rk960_oob_gpiod);
}
module_exit(rk_stub_exit);

MODULE_LICENSE("GPL");
