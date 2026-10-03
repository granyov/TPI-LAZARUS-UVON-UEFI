// SPDX-License-Identifier: GPL-2.0+
/*
 * TPI LAZARUS/UVON carrier with Forlinx FET3568-C SoM.
 *
 * Copyright (c) 2026 Tech Pro Industries LLC
 */

#include <common.h>
#include <adc.h>
#include <command.h>
#include <console.h>
#include <dm.h>
#include <env.h>
#include <g_dnl.h>
#include <init.h>
#include <version.h>
#include <asm/io.h>
#include <asm/arch-rockchip/boot_mode.h>
#include <linux/delay.h>
#include <linux/usb/ch9.h>

/*
 * RECOVERY shorts SARADC_VIN0 to ground; released, the input sits at the
 * 1.8 V reference (1023 of 1023). Under ~0.18 V counts as pressed.
 */
#define RECOVERY_ADC_CHANNEL	0
#define RECOVERY_ADC_PRESSED	100

static int recovery_adc_read(unsigned int *val)
{
	struct udevice *dev;
	struct uclass *uc;
	int ret;

	ret = uclass_get(UCLASS_ADC, &uc);
	if (ret)
		return ret;

	uclass_foreach_dev(dev, uc) {
		if (!strncmp(dev->name, "saradc", 6))
			return adc_channel_single_shot(dev->name,
						       RECOVERY_ADC_CHANNEL, val);
	}

	return -ENODEV;
}

static bool recovery_key_pressed(void)
{
	unsigned int val;
	int i, ret;

	/* Three samples 10 ms apart: a glitch must not hijack the boot. */
	for (i = 0; i < 3; i++) {
		ret = recovery_adc_read(&val);
		if (ret) {
			printf("RECOVERY: SARADC unavailable (%d)\n", ret);
			return false;
		}
		if (val > RECOVERY_ADC_PRESSED)
			return false;
		mdelay(10);
	}

	return true;
}

/*
 * The generic Rockchip check samples SARADC channel 1 and sends the board to
 * MaskROM. On UVON the key is on channel 0 and opens the recovery menu
 * instead, see rk_board_late_init().
 */
int rockchip_dnl_key_pressed(void)
{
	return 0;
}

/*
 * rockusb must keep the Rockchip ID (2207:350a) for RKDevTool, but a Windows
 * host with the Rockchip driver installed claims every gadget with that ID.
 * Mass storage therefore uses the ID of the Linux file-storage gadget, which
 * any host hands to its own class driver.
 *
 * The product string names the board and, for mass storage, what each LUN
 * is ("TPI LAZARUS UVON: eMMC, SATA" from tpi_ums_luns): the PC service tool
 * finds boards and tells eMMC from SATA by it. The serial number is serial#,
 * derived from the CPU ID, the same as Linux reports.
 *
 * bcdUSB 0x0201 marks rockusb as a loader: RKDevTool and rkdeveloptool take
 * bit 0 clear for MaskROM. The descriptor outlives a gadget, so every field
 * is set each time, or LOADER after mass storage would keep the 0525 ID.
 */
int g_dnl_bind_fixup(struct usb_device_descriptor *dev, const char *name)
{
	static char product[64];

	dev->idVendor = cpu_to_le16(CONFIG_USB_GADGET_VENDOR_NUM);
	dev->idProduct = cpu_to_le16(CONFIG_USB_GADGET_PRODUCT_NUM);
	dev->bcdUSB = cpu_to_le16(0x0200);

	if (!strcmp(name, "usb_dnl_ums")) {
		const char *luns = env_get("tpi_ums_luns");

		dev->idVendor = cpu_to_le16(0x0525);
		dev->idProduct = cpu_to_le16(0xa4a5);
		snprintf(product, sizeof(product), "TPI LAZARUS UVON%s%s",
			 luns ? ": " : "", luns ? luns : "");
		g_dnl_set_product(product);
	} else if (!strcmp(name, "usb_dnl_rockusb")) {
		dev->bcdUSB = cpu_to_le16(0x0201);
		g_dnl_set_product("TPI LAZARUS UVON: LOADER");
	} else {
		g_dnl_set_product(NULL);
	}

	return 0;
}

/*
 * Reset subcodes of the Rockchip protocol (rkdeveloptool rd N): 1 asks for
 * USB mass storage, 3 for MaskROM, anything else is a plain reset. Mass
 * storage needs no reset at all: rockusb steps aside and the recovery script
 * starts tpi_ums, so the PC tool reaches the disks without a console.
 */
#define RKUSB_RESET_MSC		1
#define RKUSB_RESET_MASKROM	3

int rkusb_set_reboot_flag(int flag)
{
	switch (flag) {
	case RKUSB_RESET_MSC:
		env_set("tpi_next", "ums");
		g_dnl_trigger_detach();
		return 1;
	case RKUSB_RESET_MASKROM:
		writel(BOOT_BROM_DOWNLOAD, CONFIG_ROCKCHIP_BOOT_MODE_REG);
		break;
	}

	return 0;
}

/*
 * Ctrl+C ends rockusb and ums but stays latched, and hush then breaks out of
 * the recovery menu loop as well. The menu clears it to come back instead.
 */
static int do_tpi_ctrlc_clear(struct cmd_tbl *cmdtp, int flag, int argc,
			      char *const argv[])
{
	clear_ctrlc();
	return CMD_RET_SUCCESS;
}

U_BOOT_CMD(tpi_ctrlc_clear, 1, 0, do_tpi_ctrlc_clear,
	   "forget the Ctrl+C that ended rockusb or ums", "");

/*
 * Printed once the console is up, right before autoboot. The cube carries the
 * TPI mark on its front face.
 */
int rk_board_late_init(void)
{
	const char *order = env_get("tpi_boot_order");

	printf("\n");
	printf("       ___________\n");
	printf("      /          /|     TPI LAZARUS UVON\n");
	printf("     /          / |     Tech Pro Industries LLC\n");
	printf("    /__________/  |\n");
	printf("    |          |  |     Bootloader: %s\n", PLAIN_VERSION);
	printf("    |   T P i  |  |     SoC:        RK3568 / Forlinx FET3568-C\n");
	printf("    |          | /      Boot order: %s\n", order ? order : "-");
	printf("    |__________|/       Recovery:   hold RECOVERY at power-on\n");
	printf("\n");

	/*
	 * preboot runs from the main loop, once the CLI is up and before the
	 * autoboot countdown; the menu then switches autoboot off itself.
	 */
	if (recovery_key_pressed()) {
		printf("RECOVERY pressed: opening the recovery menu\n");
		env_set("preboot", "setenv preboot; run tpi_recovery");
	}

	return 0;
}
