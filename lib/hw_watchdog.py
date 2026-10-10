"""Hardware watchdog (bcm2835_wdt) for the kiln controller Pi.

2026-10-08 incident: the Pi hard-locked mid-firing (dying SD card, mmc I/O
stall) and the relay latched ON; the kiln overfired ~140C because nothing
could reset a frozen machine. This class opens the watchdog device, sets the
timeout, and is fed once per control-loop iteration. If the control loop (or
the whole system) stops feeding it, the kernel reboots the Pi and the relay
drops.

Clean shutdown (SIGTERM/SIGINT from `systemctl stop`) writes the magic-close
byte ("V") before closing, so a clean stop does NOT reboot the machine.

NOTE: on this board image the real device is /dev/watchdog0. /dev/watchdog is
a stale bogus node - do not "fix" the device name to it.
"""

import fcntl
import logging
import os

log = logging.getLogger(__name__)

# Linux generic watchdog ioctls. 'W' = 0x57, int-sized payload (4 bytes).
#   _IOW(nr) = (1 << 30) | (4 << 16) | (0x57 << 8) | nr
#   _IOR(nr) = (2 << 30) | (4 << 16) | (0x57 << 8) | nr
WDI_KEEPALIVE = 0x40045700  # feed / reset the timer
WDI_SETOPTIONS = 0x40045701
WDI_SETTIMEOUT = 0x40045708
# WDS_GETSTATUS  = 0x80045702
# WDS_GETTIMEOUT = 0x80045707

WDOG_OPT_MAGICCLOSE = 0x4  # allow disarming via the magic-close byte

MAGIC_CLOSE = b"V"


class HWWatchdog(object):
    """Arms the hardware watchdog and keeps it fed.

    arm()     - open the device, request magic-close, set the timeout.
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
        """Open and arm the watchdog. Raises on failure."""
        if self.armed:
            return
        fd = os.open(self.device, os.O_WRONLY)
        try:
            # Request the magic-close option so a deliberate close() (clean
            # stop) does not leave a reboot timer running.
            try:
                fcntl.ioctl(fd, WDI_SETOPTIONS, WDOG_OPT_MAGICCLOSE)
                self.magic_close = True
            except OSError as e:
                log.warning("watchdog SETOPTIONS(MAGICCLOSE) failed: %s", e)
            # Set the reboot timeout (seconds). bcm2835_wdt accepts 1..2^31-1.
            try:
                fcntl.ioctl(fd, WDI_SETTIMEOUT, self.timeout)
            except OSError as e:
                log.warning("watchdog SETTIMEOUT(%ds) failed: %s",
                            self.timeout, e)
            self.fd = fd
            self.armed = True
            log.info("hardware watchdog armed on %s (timeout %ds, "
                     "magic_close=%s)" % (self.device, self.timeout,
                                          self.magic_close))
        except Exception:
            os.close(fd)
            raise

    def feed(self):
        """Reset the reboot timer. Returns True on success."""
        if self.fd is None:
            return False
        try:
            fcntl.ioctl(self.fd, WDI_KEEPALIVE, 0)
            return True
        except OSError as e:
            log.error("watchdog feed failed: %s", e)
            return False

    def disarm(self):
        """Magic-close then close, so the machine does NOT reboot."""
        if self.fd is None:
            return
        try:
            if self.magic_close:
                os.write(self.fd, MAGIC_CLOSE)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None
        self.armed = False
        log.info("hardware watchdog disarmed (magic close written)")
