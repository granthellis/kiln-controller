"""Hardware watchdog (bcm2835_wdt) for the kiln controller Pi.

2026-10-08 incident: the Pi hard-locked mid-firing (dying SD card, mmc I/O
stall) and the relay latched ON; the kiln overfired ~140C because nothing
could reset a frozen machine. This class opens the watchdog device, sets the
timeout, and is fed once per control-loop iteration. If the control loop (or
the whole system) stops feeding it, the kernel reboots the Pi and the relay
drops.

Clean shutdown (SIGTERM/SIGINT from `systemctl stop`) writes the magic-close
byte ("V") before closing, so a clean stop does NOT reboot the machine.

2026-10-11: the first version used wrong ioctl request numbers, so every
ioctl failed with ENOTTY and the watchdog was opened (= started, 15 s
hardware default) but never fed: the Pi reset ~15 s after the service
started, on every boot. arm() now refuses to report success unless the
timeout was set AND a keepalive was accepted, and it magic-closes on any
failure so a half-armed watchdog can never reboot the machine.

/dev/watchdog (10:130) and /dev/watchdog0 are the same bcm2835 device.
"""

import array
import fcntl
import logging
import os

log = logging.getLogger(__name__)


# Linux generic ioctl encoding (asm-generic: ARM, x86):
#   dir(2) << 30 | size(14) << 16 | type(8) << 8 | nr(8)
def _IOC(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord("W") << 8) | nr


_IOC_WRITE, _IOC_READ = 1, 2
_INT = 4
_WATCHDOG_INFO = 40  # struct watchdog_info: u32 options, u32 fw, u8 id[32]

# include/uapi/linux/watchdog.h
WDIOC_GETSUPPORT = _IOC(_IOC_READ, 0, _WATCHDOG_INFO)              # 0x80285700
WDIOC_KEEPALIVE = _IOC(_IOC_READ, 5, _INT)                         # 0x80045705
WDIOC_SETTIMEOUT = _IOC(_IOC_READ | _IOC_WRITE, 6, _INT)           # 0xc0045706
WDIOC_GETTIMEOUT = _IOC(_IOC_READ, 7, _INT)                        # 0x80045707
WDIOC_GETTIMELEFT = _IOC(_IOC_READ, 10, _INT)                      # 0x8004570a

WDIOF_SETTIMEOUT = 0x0080
WDIOF_MAGICCLOSE = 0x0100

MAGIC_CLOSE = b"V"


def _int_buf(value=0):
    # ioctls take a POINTER to an int; passing a bare int to fcntl.ioctl
    # would hand the kernel the value as an address (EFAULT).
    return array.array("i", [value])


class HWWatchdog(object):
    """Arms the hardware watchdog and keeps it fed.

    arm()     - open the device, set the timeout, prove a keepalive works.
    feed()    - reset the reboot timer (call once per control-loop pass).
    disarm()  - magic-close + close so a clean stop does not reboot.
    """

    def __init__(self, device="/dev/watchdog0", timeout=60):
        self.device = device
        self.timeout = timeout
        self.fd = None
        self.armed = False
        self.magic_close = False

    def arm(self):
        """Open and arm the watchdog. Raises on failure (never half-armed)."""
        if self.armed:
            return
        # Opening the device STARTS the hardware timer. From here on, any
        # failure must magic-close before closing or the Pi will reset.
        fd = os.open(self.device, os.O_WRONLY)
        try:
            info = bytearray(_WATCHDOG_INFO)
            fcntl.ioctl(fd, WDIOC_GETSUPPORT, info, True)
            options = int.from_bytes(info[0:4], "little")
            identity = bytes(info[8:]).split(b"\0", 1)[0].decode(errors="replace")
            self.magic_close = bool(options & WDIOF_MAGICCLOSE)
            if not options & WDIOF_SETTIMEOUT:
                raise OSError("%s (%s) cannot set a timeout" % (self.device, identity))

            buf = _int_buf(self.timeout)
            fcntl.ioctl(fd, WDIOC_SETTIMEOUT, buf, True)
            buf = _int_buf()
            fcntl.ioctl(fd, WDIOC_GETTIMEOUT, buf, True)
            if buf[0] != self.timeout:
                raise OSError("timeout readback %ds != requested %ds"
                              % (buf[0], self.timeout))

            fcntl.ioctl(fd, WDIOC_KEEPALIVE, _int_buf(), True)
        except Exception:
            self._release(fd)
            raise
        self.fd = fd
        self.armed = True
        log.info("hardware watchdog armed on %s (%s, timeout %ds, "
                 "magic_close=%s)" % (self.device, identity, self.timeout,
                                      self.magic_close))

    def feed(self):
        """Reset the reboot timer. Returns True on success."""
        if self.fd is None:
            return False
        try:
            fcntl.ioctl(self.fd, WDIOC_KEEPALIVE, _int_buf(), True)
            return True
        except OSError as e:
            log.error("watchdog feed failed: %s", e)
            self.armed = False
            return False

    def timeleft(self):
        """Seconds until reset, or None if unknown."""
        if self.fd is None:
            return None
        buf = _int_buf()
        try:
            fcntl.ioctl(self.fd, WDIOC_GETTIMELEFT, buf, True)
        except OSError:
            return None
        return buf[0]

    def disarm(self):
        """Magic-close then close, so the machine does NOT reboot."""
        if self.fd is None:
            return
        self._release(self.fd)
        self.fd = None
        self.armed = False
        log.info("hardware watchdog disarmed (magic close written)")

    def _release(self, fd):
        # Always write the magic byte: the driver ignores it if it does not
        # support magic close, and it is harmless on a stopping process.
        try:
            os.write(fd, MAGIC_CLOSE)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
