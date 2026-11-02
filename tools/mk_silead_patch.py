#!/usr/bin/env python3
"""Generate the silead.c GSLX680 (gslX6801) patch from the pristine 6.18.y file.

The board's touch controller answers as "gslX6801" in the vendor Android kernel
and needs a completely different bring-up than mainline silead.c implements:

  vendor : reset pulse -> [F0]=0x12 (download mode) -> [80]=0x03 -> [E4]=0x04
           -> [E0]=0x00 -> reset_chip -> <fw 5247 recs, 32 recs per burst>
           -> startup -> reset_chip -> startup -> read 0xB0 == 5a5a5a5a
  mainline: [E0]=0x88 -> [80]=0x0a -> [E4]=0x04 -> [E0]=0x00 -> reset
           -> <fw one 5-byte smbus msg per record> -> startup -> read 0xB0

Differences that break it: missing 0xF0 download-mode command, per-record smbus
writes (extra length byte on the wire), missing second reset/startup, and
repeated-start reads on the 0x80 window.
"""
import os
import subprocess
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silead_618.c")
REL = "drivers/input/touchscreen/silead.c"


def sub(text, old, new, count=1):
    if text.count(old) != count:
        sys.exit("pattern not found exactly %d time(s):\n%s" % (count, old[:200]))
    return text.replace(old, new, count)


src = open(SRC, encoding="utf-8").read()

src = sub(src,
          "#include <linux/unaligned.h>\n",
          "#include <linux/string.h>\n"
          "#include <linux/unaligned.h>\n")

# ---------------------------------------------------------------- defines ---
src = sub(src,
          "#define SILEAD_REG_ID\t\t0xFC\n",
          "#define SILEAD_REG_ID\t\t0xFC\n"
          "#define SILEAD_REG_PAGE\t0xF0\n")

src = sub(src,
          "#define SILEAD_CMD_RESET\t0x88\n"
          "#define SILEAD_CMD_START\t0x00\n",
          "#define SILEAD_CMD_RESET\t0x88\n"
          "#define SILEAD_CMD_START\t0x00\n"
          "#define SILEAD_CMD_DOWNLOAD\t0x12\n")

# 3 fingers: the vendor sequence programs 0x80 with 0x03 and the payload is
# 4 + max_fingers * 4 bytes long (matches the data length mainline derives).
src = sub(src,
          "#define SILEAD_TS_DATA_LEN\t44\n",
          "#define SILEAD_TS_DATA_LEN\t16\n")
src = sub(src,
          "#define SILEAD_MAX_FINGERS\t10\n",
          "#define SILEAD_MAX_FINGERS\t3\n")

# ------------------------------------------------------------ raw helpers ---
src = sub(src,
          "static bool silead_ts_handle_pen_data(struct silead_ts_data *data, u8 *buf)\n",
          """/*
 * GSLX680 native register framing: [register][data...] with no SMBus length
 * byte in between. I2C_SMBUS_I2C_BLOCK_DATA prepends one, which shifts every
 * payload by a byte and silently corrupts firmware download.
 */
static int silead_ts_write_raw(struct i2c_client *client, u8 reg,
\t\t\t       const void *data, int len)
{
\tu8 buf[129];
\tint ret;

\tif (len + 1 > (int)sizeof(buf))
\t\treturn -EINVAL;

\tbuf[0] = reg;
\tmemcpy(&buf[1], data, len);

\tret = i2c_master_send(client, buf, len + 1);
\treturn ret < 0 ? ret : 0;
}

static bool silead_ts_handle_pen_data(struct silead_ts_data *data, u8 *buf)
""")

# --------------------------------------------------------------- read path ---
# repeated-start reads on the 0x80 window time out on this chip; the vendor
# driver uses write-STOP-read (two independent transfers).
src = sub(src,
          """\terror = i2c_smbus_read_i2c_block_data(client, SILEAD_REG_DATA,
\t\t\t\t\t      SILEAD_TS_DATA_LEN, buf);
\tif (error < 0) {
\t\tdev_err(dev, "Data read error %d\\n", error);
\t\treturn;
\t}
""",
          """\tu8 reg = SILEAD_REG_DATA;

\terror = i2c_master_send(client, &reg, 1);
\tif (error < 0) {
\t\tdev_err(dev, "Data address write error %d\\n", error);
\t\treturn;
\t}

\terror = i2c_master_recv(client, buf, SILEAD_TS_DATA_LEN);
\tif (error < 0) {
\t\tdev_err(dev, "Data read error %d\\n", error);
\t\treturn;
\t}
""")

# ------------------------------------------------------------------- init ---
src = sub(src,
          """static int silead_ts_init(struct i2c_client *client)
{
\tint error;

\terror = i2c_smbus_write_byte_data(client, SILEAD_REG_RESET,
\t\t\t\t\t  SILEAD_CMD_RESET);
\tif (error)
\t\tgoto i2c_write_err;
\tusleep_range(SILEAD_CMD_SLEEP_MIN, SILEAD_CMD_SLEEP_MAX);

\terror = i2c_smbus_write_byte_data(client, SILEAD_REG_TOUCH_NR,
\t\t\t\t\t  SILEAD_MAX_FINGERS);
""",
          """static int silead_ts_init(struct i2c_client *client)
{
\tint error;

\t/*
\t * GSLX680: the firmware window (0x00-0x7F) is only reachable after the
\t * page register has been switched to the download bank. Without this
\t * command the chip answers reads but every firmware write goes nowhere.
\t */
\terror = i2c_smbus_write_byte_data(client, SILEAD_REG_PAGE,
\t\t\t\t\t  SILEAD_CMD_DOWNLOAD);
\tif (error)
\t\tgoto i2c_write_err;
\tusleep_range(2000, 3000);

\terror = i2c_smbus_write_byte_data(client, SILEAD_REG_RESET,
\t\t\t\t\t  SILEAD_CMD_RESET);
\tif (error)
\t\tgoto i2c_write_err;
\tusleep_range(SILEAD_CMD_SLEEP_MIN, SILEAD_CMD_SLEEP_MAX);

\terror = i2c_smbus_write_byte_data(client, SILEAD_REG_TOUCH_NR,
\t\t\t\t\t  SILEAD_MAX_FINGERS);
""")

# ------------------------------------------------------------------ reset ---
src = sub(src,
          """\terror = i2c_smbus_write_byte_data(client, SILEAD_REG_POWER,
\t\t\t\t\t  SILEAD_CMD_START);
\tif (error)
\t\tgoto i2c_write_err;
\tusleep_range(SILEAD_CMD_SLEEP_MIN, SILEAD_CMD_SLEEP_MAX);

\treturn 0;

i2c_write_err:
\tdev_err(&client->dev, "Chip reset error %d\\n", error);
""",
          """\t{
\t\tu32 zero = 0;

\t\terror = silead_ts_write_raw(client, SILEAD_REG_POWER, &zero,
\t\t\t\t\t    sizeof(zero));
\t}
\tif (error)
\t\tgoto i2c_write_err;
\tusleep_range(SILEAD_CMD_SLEEP_MIN, SILEAD_CMD_SLEEP_MAX);

\treturn 0;

i2c_write_err:
\tdev_err(&client->dev, "Chip reset error %d\\n", error);
""")

# --------------------------------------------------------------- load_fw ----
src = sub(src,
          """\tfw_size = fw->size / sizeof(*fw_data);
\tfw_data = (struct silead_fw_data *)fw->data;

\tfor (i = 0; i < fw_size; i++) {
\t\terror = i2c_smbus_write_i2c_block_data(client,
\t\t\t\t\t\t       fw_data[i].offset,
\t\t\t\t\t\t       4,
\t\t\t\t\t\t       (u8 *)&fw_data[i].val);
\t\tif (error) {
\t\t\tdev_err(dev, "Firmware load error %d\\n", error);
\t\t\tbreak;
\t\t}
\t}

\trelease_firmware(fw);
\treturn error ?: 0;
""",
          """\tfw_size = fw->size / sizeof(*fw_data);
\tfw_data = (struct silead_fw_data *)fw->data;

\t/*
\t * GSLX680 downloads 32 records (128 bytes) per I2C transfer, prefixed by
\t * the offset of the first record in the batch. 0xF0 is not memory: it is
\t * the page register and is always sent on its own.
\t */
\terror = 0;
\tfor (i = 0; i < fw_size; i++) {
\t\tu8 off = fw_data[i].offset;

\t\tif (fw_data[i].offset > 0xff) {
\t\t\tdev_warn(dev, "Skipping bogus fw record %u (%#x)\\n",
\t\t\t\t i, fw_data[i].offset);
\t\t\tcontinue;
\t\t}

\t\tif (off == SILEAD_REG_PAGE) {
\t\t\tu32 page = fw_data[i].val;

\t\t\terror = silead_ts_write_raw(client, SILEAD_REG_PAGE,
\t\t\t\t\t\t    &page, sizeof(page));
\t\t\tif (error) {
\t\t\t\tdev_err(dev, "Firmware page switch error %d\\n",
\t\t\t\t\terror);
\t\t\t\tbreak;
\t\t\t}
\t\t\tflag = 1;
\t\t\tcur = 1;
\t\t\tcontinue;
\t\t}

\t\tif ((flag % SILEAD_FW_BURST) == 1) {
\t\t\tbuf[0] = off;
\t\t\tcur = 1;
\t\t}
\t\tput_unaligned_le32(fw_data[i].val, &buf[cur]);
\t\tcur += 4;

\t\tif ((flag % SILEAD_FW_BURST) == 0) {
\t\t\terror = silead_ts_write_raw(client, buf[0], &buf[1],
\t\t\t\t\t\t    cur - 1);
\t\t\tif (error) {
\t\t\t\tdev_err(dev, "Firmware load error %d\\n", error);
\t\t\t\tbreak;
\t\t\t}
\t\t\tcur = 1;
\t\t}
\t\tflag++;
\t}

\tdev_info(dev, "Firmware '%s' loaded: %u records\\n", data->fw_name, i);

\trelease_firmware(fw);
\treturn error ?: 0;
""")

src = sub(src,
          """\tconst struct firmware *fw = NULL;
\tstruct silead_fw_data *fw_data;
\tunsigned int fw_size, i;
\tint error;
""",
          """\tconst struct firmware *fw = NULL;
\tstruct silead_fw_data *fw_data;
\tunsigned int fw_size, i;
\tu8 buf[SILEAD_FW_BURST * 4 + 1];
\tunsigned int cur = 1, flag = 1;
\tint error;
""")

src = sub(src,
          "#define SILEAD_MAX_FINGERS\t3\n",
          "#define SILEAD_MAX_FINGERS\t3\n"
          "#define SILEAD_FW_BURST\t\t0x20\n")

# ------------------------------------------------------------------ setup ---
src = sub(src,
          """\terror = silead_ts_load_fw(client);
\tif (error)
\t\treturn error;

\terror = silead_ts_startup(client);
\tif (error)
\t\treturn error;

\tstatus = silead_ts_get_status(client);
""",
          """\terror = silead_ts_load_fw(client);
\tif (error)
\t\treturn error;

\terror = silead_ts_startup(client);
\tif (error)
\t\treturn error;

\t/*
\t * GSLX680 only jumps into the freshly downloaded firmware after a second
\t * reset/startup cycle. Skipping it leaves the chip in the ROM bootloader:
\t * it replies on I2C, but 0xB0 never becomes 0x5a5a5a5a.
\t */
\terror = silead_ts_reset(client);
\tif (error)
\t\treturn error;

\terror = silead_ts_startup(client);
\tif (error)
\t\treturn error;

\tstatus = silead_ts_get_status(client);
""")

# ------------------------------------------------------------------ write ---
out_root = tempfile.mkdtemp(prefix="sileadpatch")
a_path = os.path.join(out_root, "a", REL)
b_path = os.path.join(out_root, "b", REL)
os.makedirs(os.path.dirname(a_path), exist_ok=True)
os.makedirs(os.path.dirname(b_path), exist_ok=True)

open(a_path, "w", encoding="utf-8").write(open(SRC, encoding="utf-8").read())
open(b_path, "w", encoding="utf-8").write(src)

diff = subprocess.run(
    ["diff", "-u", "--label", "a/" + REL, "--label", "b/" + REL, a_path, b_path],
    capture_output=True, text=True)
if diff.returncode != 1:
    sys.exit("diff failed: %r" % diff.stderr)

patch_path = sys.argv[1] if len(sys.argv) > 1 else "silead-gslx680.patch"
open(patch_path, "w", encoding="utf-8", newline="\n").write(diff.stdout)
print("wrote %s (%d bytes, %d hunks)" %
      (patch_path, len(diff.stdout), diff.stdout.count("\n@@")))
