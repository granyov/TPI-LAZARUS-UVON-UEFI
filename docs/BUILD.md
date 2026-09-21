# Сборка прошивки из исходников

Прошивка собирается из апстримного U-Boot с небольшой дельтой TPI. Заводские
DDR/SPL, TF-A и OP-TEE не пересобираются: они берутся из авторизованных
vendor-образов и упаковываются без изменений, их SHA-256 проверяются на каждом
запуске.

## Требования к хосту

Проверено на Debian 13 (trixie), x86_64.

```sh
sudo apt-get install -y gcc-aarch64-linux-gnu build-essential bison flex \
  libssl-dev device-tree-compiler swig python3-dev python3-setuptools \
  python3-pyelftools bc uuid-dev libgnutls28-dev git
```

Нужно около 3 ГБ свободного места: дерево U-Boot занимает ~220 МБ, каталог
сборки — около 1 ГБ.

## Vendor-входы

Два файла, в репозиторий они не входят:

| Путь | SHA-256 | Что берётся |
|---|---|---|
| `vendor/UVON-original-uefi-fit.img` | `dc2ba2ee4d1dca09dd2e5dd307a2f4609a7c2e477ad714ba20a5192b3e20e462` | шесть payload'ов TF-A |
| `vendor/uboot-forlinx.img` | `d691666231a2ec46b52f72e2f25e00ec226724effb02b03113908ef03eae9dfb` | payload OP-TEE |

Первый — сохранённый раздел `uboot` с заводским UEFI, второй — заводской U-Boot
из образа Ubuntu для OK3568-C. Оба описаны в `документации на vendor-образы.

## Дельта TPI

Всё лежит в `src/`:

| Файл | Назначение |
|---|---|
| `tpi-lazarus-rk3568_defconfig` | конфигурация платы |
| `rk3568-tpi-lazarus.dts` | device tree платы |
| `rk3568-tpi-lazarus-u-boot.dtsi` | U-Boot-специфичные дополнения DT |
| `board/tpi/lazarus/` | board-файл с баннером загрузки |
| `dts-makefile.patch` | регистрация DTB в сборке |
| `rk3568-board-target.patch` | объявление платы `TARGET_TPI_LAZARUS_RK3568` |
| `rk3568-dram-high-bank.patch` | второй банк DRAM на `0x1f0000000` |
| `pylibfdt-swig43.patch` | совместимость `pylibfdt` со SWIG 4.3 из Debian 13 |

## Порядок сборки

```sh
git clone --depth 1 --branch v2024.04 https://github.com/u-boot/u-boot u-boot
cp src/tpi-lazarus-rk3568_defconfig u-boot/configs/
cp src/rk3568-tpi-lazarus.dts tpi-src/rk3568-tpi-lazarus-u-boot.dtsi u-boot/arch/arm/dts/
cp -r src/board/tpi u-boot/board/
(cd u-boot && git apply ../src/*.patch)

export CROSS_COMPILE=aarch64-linux-gnu- SOURCE_DATE_EPOCH=1789775133
make -C u-boot O=../build tpi-lazarus-rk3568_defconfig
make -C u-boot O=../build -j"$(nproc)"
```

Два замечания по сборке.

Финальный шаг `binman` завершается ошибкой: он хочет собственные
`ROCKCHIP_TPL`, `BL31` и `TEE` для своего варианта образа. Для этой цепочки он
не нужен — всё необходимое (`u-boot-nodtb.bin`, DTB и `tools/mkimage`) создаётся
до него.

Собирать нужно с отвязанным stdin (`</dev/null` уже подразумевается в примере
выше при неинтерактивном запуске): включённый download-гаджет требует
`FASTBOOT_BUF_ADDR`, у которого в Kconfig нет значения по умолчанию, и без
ответа `conf --syncconfig` уходит в бесконечный опрос с сообщением
`Error in reading or end of file`. В нашем defconfig значение задано, но при
изменении конфигурации об этом стоит помнить.

## Упаковка образа

```sh
python3 tools/build_fit.py
```

Версия релиза задаётся одной константой `VERSION` в начале `tools/build_fit.py` — от
неё берутся имена всех выходных файлов. Три переменные окружения позволяют не
править скрипт, если дерево разложено иначе:

| Переменная | Что заменяет |
|---|---|
| `TPI_BUILD_DIR` | каталог сборки относительно `builders/uboot-2024/` (по умолчанию `build`) |
| `TPI_VENDOR_UEFI_FIT` | путь к `UVON-original-uefi-fit.img` |
| `TPI_VENDOR_UBOOT_FIT` | путь к `uboot-forlinx.img` |

Подменить vendor-вход на произвольный файл это не даёт: SHA-256 обоих входов
сверяются с записанными в любом случае.

Скрипт извлекает шесть payload'ов TF-A и OP-TEE из vendor-входов, сверяет их
SHA-256 с записанными, формирует `.its`, вызывает `mkimage`, проверяет
получившийся FIT через `dumpimage` и укладывает **две идентичные копии** в
4-мегабайтный образ — на смещения `0x0` и `0x200000`, как в заводском образе.

Результат появляется в `output/`: сам образ,
chainload-файл для проверки из оперативной памяти и манифест с составом.

## Воспроизводимость

Опубликованные образы собраны `aarch64-linux-gnu-gcc 14.2.0` при
`SOURCE_DATE_EPOCH=1789775133`. Другой компилятор даст другой BL33: контрольная
сборка тем же деревом, но `aarch64-elf-gcc 16.2.0`, отличалась по размеру.
При этом **control DTB совпадает побайтно** — его компилирует встроенный в
U-Boot dtc.

## Установка собранного образа

См. [`docs/INSTALL-CLEAN-BOARD.md`](INSTALL-CLEAN-BOARD.md).
