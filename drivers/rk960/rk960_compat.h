/* SPDX-License-Identifier: GPL-2.0 */
/*
 * rk960_compat.h - Linux 6.x API compatibility shims for the RK960 driver.
 * Force-included into every translation unit via ccflags-y += -include in
 * the Makefile, so no per-file edits are needed.
 */
#ifndef RK960_COMPAT_H
#define RK960_COMPAT_H

#include <linux/version.h>

/* 6.16 removed from_timer(); the new container_of-style macro is
 * timer_container_of() (introduced 6.15). Same signature/semantics. */
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 16, 0)
#define from_timer(var, timer, field) timer_container_of(var, timer, field)
#endif

/* 6.15 renamed the timer deletion API; del_timer_sync() removed in 6.18. */
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 15, 0)
#define del_timer_sync timer_delete_sync
#define del_timer timer_delete
#endif

/* 6.16 removed ieee80211_tx_status(); mainline cw1200 uses _ni() in the
 * same place (rk960_skb_dtor is a process-context skb destructor). */
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 16, 0)
#define ieee80211_tx_status(hw, skb) ieee80211_tx_status_ni(hw, skb)
#endif

/* debug.c uses vmalloc/vfree without including the header. */
#include <linux/vmalloc.h>

#endif /* RK960_COMPAT_H */
