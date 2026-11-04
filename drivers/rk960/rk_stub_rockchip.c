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
 * high.  So look the line up and return the mapped IRQ here.
 *
 * The vendor tree reads the line with the BSP-only
 * of_get_named_gpio(node, "WIFI,host_wake_irq", 0), which uses the property
 * name verbatim.  The gpiod consumer API instead derives the property name
 * from the connection id ("<con_id>-gpios" / "<con_id>-gpio"), so the board
 * DTS carries a "WIFI,host_wake_irq-gpios" alias next to the vendor literal.
 * Both are tried here.
 *
 * MAC provisioning comes from the chip efuse inside the firmware, with a
 * random address as final fallback, so rockchip_wifi_mac_addr() reports
 * "not available".
 */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_irq.h>
#include <linux/of_gpio.h>
#include <linux/gpio.h>
#include <linux/gpio/consumer.h>
#include <linux/rfkill-wlan.h>

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

static int rk960_oob_irq_lookup(void)
{
	struct device_node *np;
	struct gpio_desc *desc;
	int irq = 0;
	int gpio;

	np = of_find_compatible_node(NULL, NULL, "wlan-platdata");
	if (!np)
		return 0;

	desc = fwnode_gpiod_get_index(of_fwnode_handle(np),
				      "WIFI,host_wake_irq", 0,
				      GPIOD_IN, "rk960-oob");
	if (!IS_ERR(desc)) {
		rk960_oob_gpiod = desc;
		irq = gpiod_to_irq(desc);
	} else {
		/* Fall back to the vendor literal property name, which the
		 * gpiod name mangling above can never reach. */
		gpio = of_get_named_gpio(np, "WIFI,host_wake_irq", 0);
		if (gpio >= 0)
			irq = gpio_to_irq(gpio);
		else
			irq = gpio;
	}

	of_node_put(np);

	if (irq <= 0) {
		pr_err("rk960: OOB host-wake line unusable (%d), falling back to in-band SDIO irq\n",
		       irq);
		return 0;
	}

	pr_info("rk960: OOB host-wake irq %d (%s)\n", irq,
		rk960_oob_gpiod ? "gpiod" : "legacy gpio");
	return irq;
}

int rockchip_wifi_get_oob_irq(void)
{
	return rk960_oob_irq_lookup();
}
EXPORT_SYMBOL_GPL(rockchip_wifi_get_oob_irq);

int rockchip_wifi_mac_addr(unsigned char *buf)
{
	return -1;
}
EXPORT_SYMBOL_GPL(rockchip_wifi_mac_addr);

/* Called from rk960_sdio_exit().  This file must not declare module_exit()
 * itself: the module's init/exit live in sdio.c and a second cleanup_module
 * makes the link fail with "multiple definition of cleanup_module". */
void rk_stub_rockchip_release(void)
{
	gpiod_put(rk960_oob_gpiod);
	rk960_oob_gpiod = NULL;
}
EXPORT_SYMBOL_GPL(rk_stub_rockchip_release);

MODULE_LICENSE("GPL");
