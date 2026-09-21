#!/usr/bin/env python3
"""Package TPI U-Boot 2024.04 with the proven Forlinx TF-A payloads.

The archived 4 MiB FIT is used only as the authorized source of the six
TF-A payloads. DDR initialization and SPL live outside this image and are not
modified. The resulting image is padded to the existing 4 MiB eMMC uboot
partition size.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


VERSION = "v3.7"

ROOT = Path(__file__).resolve().parent
SOURCE_TREE = ROOT / "u-boot"
BUILD = ROOT / os.environ.get("TPI_BUILD_DIR", "build")
VENDOR_FIT = Path(os.environ.get("TPI_VENDOR_UEFI_FIT",
                                 ROOT.parent / "uefi" / "vendor" / "UVON-original-uefi-fit.img"))
OUTPUT = ROOT / "output"
COMPONENT_DIR = OUTPUT / "components"

MKIMAGE = BUILD / "tools" / "mkimage"
DUMPIMAGE = BUILD / "tools" / "dumpimage"
BL33 = BUILD / "u-boot-nodtb.bin"
DTB = BUILD / "arch" / "arm" / "dts" / "rk3568-tpi-lazarus.dtb"
DEFCONFIG = SOURCE_TREE / "configs" / "tpi-lazarus-rk3568_defconfig"

OUT_FIT = OUTPUT / f"TPI-LAZARUS-U-Boot-2024.04-SATA-UEFI-{VERSION}.img"
OUT_CHAINLOAD = OUTPUT / f"TPI-LAZARUS-U-Boot-2024.04-SATA-UEFI-{VERSION}-chainload.bin"
OUT_ITS = OUTPUT / f"tpi-lazarus-{VERSION}.its"
OUT_MANIFEST = OUTPUT / f"manifest-{VERSION}.json"
OUT_DUMPIMAGE = OUTPUT / f"dumpimage-{VERSION}.txt"
OUT_SUMS = OUTPUT / f"SHA256SUMS-{VERSION}"

VENDOR_FIT_SHA256 = "dc2ba2ee4d1dca09dd2e5dd307a2f4609a7c2e477ad714ba20a5192b3e20e462"

# OP-TEE берётся из заводского uboot-FIT: TF-A стартует opteed, и без этого
# payload'а secure-мир остаётся без OS ("Error initializing runtime service").
VENDOR_UBOOT_FIT = Path(os.environ.get("TPI_VENDOR_UBOOT_FIT",
                                       ROOT.parent / "uboot" / "vendor" / "uboot-forlinx.img"))
VENDOR_UBOOT_FIT_SHA256 = "d691666231a2ec46b52f72e2f25e00ec226724effb02b03113908ef03eae9dfb"
OPTEE = (0x18A400, 0x0709A0, 0x08400000,
         "4fcbcd38704b593e961cd90910d9ca38fd72d2fb382819a17c77538776adbd53")
FIT_DATA_BASE = 0x0E00
PARTITION_SIZE = 4 * 1024 * 1024
COPY_STRIDE = 2 * 1024 * 1024  # вторая (резервная) копия FIT, как у vendor

TF_A = {
    "atf-1": (0x099A00, 0x029000, 0x00040000, 0x00040000,
              "b5946ac63df8fb3569407a75cf2f6aa396551ba011e1a84bec654dc9982ba063"),
    "atf-2": (0x0C2A00, 0x001EEC, 0x00069000, None,
              "a9a1e63bef11a6776a9670708fe78211ddcc437cc4ab145e1cfef77cea8607e4"),
    "atf-3": (0x0C4A00, 0x004F43, 0x0006B000, None,
              "2f91089eb714c78d9fb81f005859beda7f1709e04a858e4db732cb8f9800e727"),
    "atf-4": (0x0C9A00, 0x00A000, 0xFDCC1000, None,
              "b8dca786b41f8beb12e2434c1698e344931777099aa0e5729b76fcda2f781907"),
    "atf-5": (0x0D3A00, 0x002000, 0xFDCCE000, None,
              "86ef8857484c5cd51363c3dd8338818c7bdc687e48c57897578781f10270a515"),
    "atf-6": (0x0D5A00, 0x002000, 0xFDCD0000, None,
              "0b2b146c608fb46195852ab008f179c3e4ea399d38af589691d72705fbfde654"),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def run(*args: str) -> str:
    result = subprocess.run(args, check=True, text=True, capture_output=True)
    return result.stdout + result.stderr


def validate_inputs() -> tuple[bytes, dict[str, Path]]:
    for path in (MKIMAGE, DUMPIMAGE, BL33, DTB, DEFCONFIG, VENDOR_FIT, VENDOR_UBOOT_FIT):
        if not path.is_file():
            raise FileNotFoundError(path)

    vendor = VENDOR_FIT.read_bytes()
    if len(vendor) != PARTITION_SIZE or sha256(vendor) != VENDOR_FIT_SHA256:
        raise ValueError("archived vendor FIT size/hash mismatch")

    bl33 = BL33.read_bytes()
    required = (
        f"U-Boot 2024.04-tpi-lazarus-{VERSION}".encode(),
        b"TPI LAZARUS UVON",
        b"Tech Pro Industries LLC",
        b"TPI-LAZARUS=> ",
        b"bootcmd=scsi scan; bootflow scan -lb",
        b"/EFI/BOOT/BOOTAA64.EFI",
        b"ubootefi.var",
        b"dwc_ahci",
    )
    missing = [item.decode() for item in required if item not in bl33]
    if missing:
        raise ValueError(f"BL33 lacks required features/branding: {missing}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    COMPONENT_DIR.mkdir(parents=True, exist_ok=True)
    components: dict[str, Path] = {}
    for name, (relative, size, _load, _entry, expected) in TF_A.items():
        payload = vendor[FIT_DATA_BASE + relative:FIT_DATA_BASE + relative + size]
        actual = sha256(payload)
        if actual != expected:
            raise ValueError(f"{name} source hash mismatch: {actual}")
        target = COMPONENT_DIR / f"{name}.bin"
        target.write_bytes(payload)
        components[name] = target

    vendor_uboot = VENDOR_UBOOT_FIT.read_bytes()
    if sha256(vendor_uboot) != VENDOR_UBOOT_FIT_SHA256:
        raise ValueError("archived vendor U-Boot FIT size/hash mismatch")
    off, size, _load, expected = OPTEE
    payload = vendor_uboot[off:off + size]
    if sha256(payload) != expected:
        raise ValueError(f"optee source hash mismatch: {sha256(payload)}")
    optee_path = COMPONENT_DIR / "optee.bin"
    optee_path.write_bytes(payload)
    components["optee"] = optee_path

    shutil.copyfile(BL33, COMPONENT_DIR / "u-boot-nodtb.bin")
    shutil.copyfile(DTB, COMPONENT_DIR / "rk3568-tpi-lazarus.dtb")
    return vendor, components


def make_its(components: dict[str, Path]) -> str:
    image_nodes = []
    for name, (_relative, _size, load, entry, _expected) in TF_A.items():
        entry_line = f"\n            entry = <0x{entry:08x}>;" if entry is not None else ""
        image_nodes.append(f'''        {name} {{
            description = "Proven Forlinx ARM Trusted Firmware";
            data = /incbin/("{components[name]}");
            type = "firmware";
            arch = "arm64";
            os = "arm-trusted-firmware";
            compression = "none";
            load = <0x{load:08x}>;{entry_line}
            hash-1 {{ algo = "sha256"; }};
        }};''')
    return f'''/dts-v1/;

/ {{
    description = "TPI LAZARUS U-Boot 2024.04 SATA UEFI with proven Forlinx TF-A";
    #address-cells = <1>;

    images {{
        u-boot {{
            description = "TPI LAZARUS U-Boot 2024.04 UEFI";
            data = /incbin/("{COMPONENT_DIR / 'u-boot-nodtb.bin'}");
            type = "standalone";
            os = "U-Boot";
            arch = "arm64";
            compression = "none";
            load = <0x00a00000>;
            entry = <0x00a00000>;
            hash-1 {{ algo = "sha256"; }};
        }};

{os.linesep.join(image_nodes)}

        optee {{
            description = "Proven Forlinx OP-TEE";
            data = /incbin/("{components['optee']}");
            type = "firmware";
            arch = "arm64";
            os = "op-tee";
            compression = "none";
            load = <0x08400000>;
            hash-1 {{ algo = "sha256"; }};
        }};

        fdt-1 {{
            description = "TPI LAZARUS UVON SATA2 control DT";
            data = /incbin/("{COMPONENT_DIR / 'rk3568-tpi-lazarus.dtb'}");
            type = "flat_dt";
            compression = "none";
            hash-1 {{ algo = "sha256"; }};
        }};
    }};

    configurations {{
        default = "conf-tpi-lazarus";
        conf-tpi-lazarus {{
            description = "TPI LAZARUS UVON / Forlinx FET3568-C";
            firmware = "atf-1";
            loadables = "u-boot", "atf-2", "atf-3", "atf-4", "atf-5", "atf-6", "optee";
            fdt = "fdt-1";
        }};
    }};
}};
'''


def verify_fit() -> dict[str, str]:
    listing = run(str(DUMPIMAGE), "-l", str(OUT_FIT))
    required_listing = (
        "TPI LAZARUS U-Boot 2024.04 UEFI",
        "TPI LAZARUS UVON SATA2 control DT",
        "Configuration 0 (conf-tpi-lazarus)",
    )
    for text in required_listing:
        if text not in listing:
            raise ValueError(f"FIT listing missing: {text}")

    expected = {
        "u-boot": file_sha256(BL33),
        **{name: values[4] for name, values in TF_A.items()},
        "optee": OPTEE[3],
        "fdt-1": file_sha256(DTB),
    }
    extracted: dict[str, str] = {}
    for index, name in enumerate(expected):
        target = COMPONENT_DIR / f"verified-{name}.bin"
        run(str(DUMPIMAGE), "-T", "flat_dt", "-p", str(index), "-o", str(target), str(OUT_FIT))
        actual = file_sha256(target)
        if actual != expected[name]:
            raise ValueError(f"packed {name} hash mismatch: {actual}")
        extracted[name] = actual
    OUT_DUMPIMAGE.write_text(listing)
    return extracted


def main() -> None:
    _vendor, components = validate_inputs()
    OUT_ITS.write_text(make_its(components))

    unpadded = OUTPUT / f"tpi-lazarus-{VERSION}.unpadded.itb"
    run(str(MKIMAGE), "-E", "-B", "0x200", "-p", "0x1000", "-f", str(OUT_ITS), str(unpadded))
    fit = unpadded.read_bytes()
    if len(fit) > COPY_STRIDE:
        raise ValueError(
            f"FIT {len(fit)} bytes does not fit the {COPY_STRIDE}-byte copy slot")
    if len(fit) > PARTITION_SIZE:
        raise ValueError(f"FIT does not fit 4 MiB partition: {len(fit)}")
    # Заводской образ хранит FIT дважды: на 0x0 и на COPY_STRIDE. Rockchip SPL
    # использует вторую копию как резервную, поэтому воспроизводим раскладку.
    image = bytearray(PARTITION_SIZE)
    image[0:len(fit)] = fit
    image[COPY_STRIDE:COPY_STRIDE + len(fit)] = fit
    OUT_FIT.write_bytes(bytes(image))
    OUT_CHAINLOAD.write_bytes(BL33.read_bytes() + DTB.read_bytes())

    packed_hashes = verify_fit()
    source_commit = run("git", "-C", str(SOURCE_TREE), "rev-parse", "HEAD").strip()
    manifest = {
        "schema": 2,
        "product": "TPI LAZARUS/UVON U-Boot 2024.04 SATA UEFI",
        "vendor": "Tech Pro Industries LLC (TPI)",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "deployment_status": "built-and-statically-verified; hardware-test-required-before-emmc",
        "architecture": {
            "unchanged": ["BootROM", "Forlinx DDR/early loader", "Forlinx SPL", "Forlinx TF-A BL31 payloads"],
            "replaced": "BL33 and its U-Boot control DTB",
            "bl33_load_entry": "0x00a00000",
        },
        "upstream": {
            "project": "https://github.com/u-boot/u-boot",
            "tag": "v2024.04",
            "commit": source_commit,
            "defconfig_sha256": file_sha256(DEFCONFIG),
        },
        "inputs": {
            "vendor_fit_sha256": VENDOR_FIT_SHA256,
            "bl33_sha256": file_sha256(BL33),
            "control_dtb_sha256": file_sha256(DTB),
        },
        "outputs": {
            "fit": {"file": OUT_FIT.name, "size": OUT_FIT.stat().st_size, "sha256": file_sha256(OUT_FIT)},
            "chainload": {"file": OUT_CHAINLOAD.name, "size": OUT_CHAINLOAD.stat().st_size,
                          "sha256": file_sha256(OUT_CHAINLOAD)},
        },
        "packed_component_sha256": packed_hashes,
        "features": [
            "native RK3568 SATA2 through DWC AHCI and SCSI block layer",
            "standard boot with SATA scan and bootflow",
            "UEFI loader, UEFI boot manager, EFI variable file store",
            "GPT, FAT, ext4, USB, MMC and network fallback",
            "UART2 115200 8N1 and interactive TPI-LAZARUS prompt",
        ],
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    sums = [OUT_FIT, OUT_CHAINLOAD, OUT_ITS, OUT_MANIFEST, OUT_DUMPIMAGE]
    OUT_SUMS.write_text("".join(f"{file_sha256(p)}  {p.name}\n" for p in sums))
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
