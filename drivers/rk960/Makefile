ifeq ($(CONFIG_RK960),)
CONFIG_RK960=m
endif

NAME = rk960

OBJS := \
	fwio.o \
	txrx.o \
	main.o \
	queue.o \
	hwio.o \
	bh.o \
	wsm.o \
	sta.o \
	ap.o \
	scan.o \
	debug.o \
	pm.o \
	sdio.o \
	vendor.o

ifeq ($(CONFIG_RK960_ITP),y)
OBJS += itp.o
endif

# BSP helper stubs + local <linux/rfkill-wlan.h> shim + 6.x API compat
OBJS += rk_stub_rockchip.o
ccflags-y += -I$(src)/include
ccflags-y += -include $(src)/rk960_compat.h

#EXTRA_CFLAGS += -DROAM_OFFLOAD
ccflags-y += -DHW_RESET
#EXTRA_CFLAGS += -DP2P_MULTIVIF
#EXTRA_CFLAGS += -DCUSTOM_FEATURE
#EXTRA_CFLAGS += -DMCAST_FWDING
ccflags-y += -DRK960_SUSPEND_RESUME_FILTER_ENABLE
ccflags-y += -DAP_AGGREGATE_FW_FIX
ccflags-y += -DAP_HT_CAP_UPDATE
ccflags-y += -DROC_DEBUG
# Extra IE for probe response from upper layer is needed in P2P GO
# For offloading probe response to FW, the extra IE must be included
# in the probe response template
ccflags-y += -DPROBE_RESP_EXTRA_IE
#EXTRA_CFLAGS += -DIPV6_FILTERING

#EXTRA_CFLAGS += -DCONFIG_RK960_5GHZ_SUPPORT
#EXTRA_CFLAGS += -DCONFIG_RK960_WAPI_SUPPORT
#EXTRA_CFLAGS += -DCONFIG_RK960_USE_STE_EXTENSIONS
#EXTRA_CFLAGS += -DCONFIG_RK960_DISABLE_BEACON_HINTS
ccflags-y += -DCONFIG_RK960_DEBUGFS
#EXTRA_CFLAGS += -DCONFIG_RK960_WSM_DUMPS
#EXTRA_CFLAGS += -DCONFIG_RK960_WSM_DUMPS_SHORT
#EXTRA_CFLAGS += -DCONFIG_RK960_ITP
#EXTRA_CFLAGS += -DIBSS_SUPPORT
#EXTRA_CFLAGS += -DCUSTOM_REG_SET
#EXTRA_CFLAGS += -DENABLE_DBGFS_WRITE
#EXTRA_CFLAGS += -DSUPPORT_FWCR
#EXTRA_CFLAGS += -DDISABLE_TX_POLICY

ccflags-y += -Wno-date-time

obj-$(CONFIG_RK960) += $(NAME).o
$(NAME)-objs= $(OBJS)

#EXTRA_CFLAGS += -g
# -Wno-incompatible-pointer-types-discards-qualifiers 是 clang 专用标志
ccflags-y += -Wno-unused-variable

ifneq ($(KERNELRELEASE),)

#EXTRA_LDFLAGS += --strip-debug

else

all:
	@make -C $(KROOT) M=$(PWD) modules

clean:
	#@make -C $(KROOT) M=$(PWD) clean
	rm -f *.o *.mod.c *.mod *.cmd *.ko

endif

