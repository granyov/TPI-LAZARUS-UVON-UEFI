/* SPDX-License-Identifier: GPL-2.0+ */
/*
 * TPI LAZARUS/UVON carrier with Forlinx FET3568-C SoM.
 *
 * Copyright (c) 2026 Tech Pro Industries LLC
 */

#ifndef __TPI_LAZARUS_RK3568_H
#define __TPI_LAZARUS_RK3568_H

/*
 * The only variables U-Boot takes from the environment saved on eMMC
 * (CONFIG_ENV_WRITEABLE_LIST). Everything else, boot scripts included, always
 * comes from board/tpi/lazarus/lazarus.env, so a firmware update cannot be
 * shadowed by a stale saved copy, and a mistyped saveenv cannot take the
 * console or autoboot away.
 */
#define CFG_ENV_FLAGS_LIST_STATIC	"tpi_boot_order:sw"

#include <configs/rk3568_common.h>

#define ROCKCHIP_DEVICE_SETTINGS \
			"stdout=serial,vidconsole\0" \
			"stderr=serial,vidconsole\0"

#endif
