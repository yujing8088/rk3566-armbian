/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Local shim for <linux/rfkill-wlan.h> (Rockchip BSP-only header, not
 * present in mainline kernels). Provides just the four helpers the RK960
 * driver calls; see rk_stub_rockchip.c for the implementations.
 */
#ifndef _RFKILL_WLAN_SHIM_H
#define _RFKILL_WLAN_SHIM_H

/* Power the WiFi module on/off (BSP: toggles WLAN_REG_ON gpio). */
int rockchip_wifi_power(int on);

/* Tell the mmc host to (re)scan the SDIO bus. */
int rockchip_wifi_set_carddetect(int val);

/* Return the OOB interrupt number configured for the module (0 = none,
 * driver then falls back to polling). */
int rockchip_wifi_get_oob_irq(void);

/* Fetch a MAC address provisioned by the vendor bootloader (0 on success,
 * nonzero = not available, driver falls back to efuse / random addr). */
int rockchip_wifi_mac_addr(unsigned char *buf);

/* Drop the OOB host-wake GPIO descriptor again (called from module exit;
 * the stub cannot use module_exit() itself, sdio.c owns that). */
void rk_stub_rockchip_release(void);

#endif /* _RFKILL_WLAN_SHIM_H */
