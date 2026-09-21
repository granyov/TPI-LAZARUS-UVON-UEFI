// SPDX-License-Identifier: GPL-2.0+
/*
 * TPI LAZARUS/UVON carrier with Forlinx FET3568-C SoM.
 *
 * Copyright (c) 2026 Tech Pro Industries LLC
 */

#include <common.h>
#include <init.h>
#include <version.h>

/*
 * Printed once the console is up, right before autoboot. The cube carries the
 * TPI mark on its front face.
 */
int rk_board_late_init(void)
{
	printf("\n");
	printf("       ___________\n");
	printf("      /          /|     TPI LAZARUS UVON\n");
	printf("     /          / |     Tech Pro Industries LLC\n");
	printf("    /__________/  |\n");
	printf("    |          |  |     Bootloader: %s\n", PLAIN_VERSION);
	printf("    |   T P i  |  |     SoC:        RK3568 / Forlinx FET3568-C\n");
	printf("    |          | /\n");
	printf("    |__________|/\n");
	printf("\n");

	return 0;
}
