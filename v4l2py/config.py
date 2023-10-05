#
# This file is part of the v4l2py project
#
# Copyright (c) 2021 Tiago Coutinho
# Distributed under the GPLv3 license. See LICENSE for more info.

import logging
import pathlib
import configparser

from .device import Device, V4L2Error

log = logging.getLogger(__name__)


class ConfigurationError(V4L2Error):
    pass


class CompatibilityError(V4L2Error):
    pass


class DeviceStateError(V4L2Error):
    pass


class ConfigManager:
    def __init__(self, device: Device):
        self.device = device
        self.log = log.getChild(f"{device.filename.stem}")
        self.config = None
        self.filename = None

    @property
    def has_config(self) -> bool:
        return (
            isinstance(self.config, configparser.ConfigParser)
            and self.config.sections()
        )

    @property
    def config_loaded(self) -> bool:
        return self.filename is not None

    def reset(self) -> None:
        self.config = configparser.ConfigParser()
        self.filename = None

    def acquire(self) -> None:
        self.log.info(f"acquiring configuration from {self.device.filename}")
        if not self.has_config:
            self.reset()

        self.config["device"] = {
            "driver": str(self.device.info.driver),
            "card": str(self.device.info.card),
            "bus_info": str(self.device.info.bus_info),
            "version": str(self.device.info.version),
            "legacy_controls": str(self.device.legacy_controls),
        }
        self.config["controls"] = {}
        for c in self.device.controls.values():
            self.config["controls"][c.config_name] = str(c.value)
        self.log.info("configuration successfully acquired")

    def save(self, filename) -> None:
        self.log.info(f"writing configuration to {filename}")
        if isinstance(filename, pathlib.Path):
            pass
        elif isinstance(filename, str):
            filename = pathlib.Path(filename)
        else:
            raise TypeError(
                f"filename expected to be str or pathlib.Path, not {filename.__class__.__name__}"
            )

        if self.device.closed:
            raise V4L2Error(f"{self.device} must be opened to save configuration")
        if not self.config or not self.config.sections():
            self.acquire()

        with filename.open(mode="wt") as configfile:
            self.config.write(configfile)
        self.log.info(f"configuration written to {filename.resolve()}")

    def load(self, filename) -> None:
        self.log.info(f"reading configuration from {filename}")
        if isinstance(filename, pathlib.Path):
            pass
        elif isinstance(filename, str):
            filename = pathlib.Path(filename)
        else:
            raise TypeError(
                f"filename expected to be str or pathlib.Path, not {filename.__class__.__name__}"
            )

        if not (filename.exists() and filename.is_file()):
            raise RuntimeError(f"{filename} must be an existing file")
        if self.device.closed:
            raise V4L2Error(f"{self.device} must be opened to load configuration")

        self.reset()
        res = self.config.read((filename,))
        if not res:
            raise RuntimeError(f"Failed to read configuration from {filename}")
        else:
            filename = pathlib.Path(res[0])
            self.filename = filename.resolve()
        self.log.info(f"configuration read from {self.filename}")

    def validate(self, pedantic: bool = False) -> None:
        self.log.info("validating configuration")
        if not self.config_loaded:
            raise RuntimeError("Load configuration first")

        for section in ("controls",):
            if not self.config.has_section(section):
                raise ConfigurationError(f"Mandatory section '{section}' is missing")
        controls = self.device.controls.named_keys()
        for ctrl, _ in self.config.items("controls"):
            if ctrl not in controls:
                raise CompatibilityError(
                    f"{self.device.filename} has no control named {ctrl}"
                )

        if pedantic:
            if not self.config.has_section("device"):
                raise ConfigurationError("Section 'device' is missing")
            for option, have in (
                ("card", str(self.device.info.card)),
                ("driver", str(self.device.info.driver)),
                ("version", str(self.device.info.version)),
                ("legacy_controls", str(self.device.legacy_controls)),
            ):
                want = self.config["device"][option]
                if not (want == have):
                    raise CompatibilityError(
                        f"{option.title()} mismatch: want '{want}', have '{have}'"
                    )
        self.log.info("configuration validated")

    def apply(self, cycles: int = 2) -> None:
        self.log.info("applying configuration")
        if not self.config_loaded:
            raise RuntimeError("Load configuration first")
        if self.device.closed:
            raise V4L2Error(f"{self.device} must be opened to apply configuration")

        for cycle in range(1, cycles + 1):
            for ctrl, value in self.config.items("controls"):
                what = f"#{cycle}/{cycles} {ctrl}"
                if self.device.controls[ctrl].is_writeable:
                    if not self.device.controls[ctrl].is_flagged_write_only:
                        cur = f"{self.device.controls[ctrl].value}"
                    else:
                        cur = "<not_readable>"
                    self.log.debug(f"{what} {cur} => {value}")
                    self.device.controls[ctrl].value = value
                else:
                    self.log.debug(f"{what} skipped (not writeable)")
        self.log.info("configuration applied")

    def verify(self) -> None:
        self.log.info("verifying device configuration")
        if not self.config_loaded:
            raise RuntimeError("Load configuration first")
        if self.device.closed:
            raise V4L2Error(f"{self.device} must be opened to verify configuration")

        for ctrl, value in self.config.items("controls"):
            if not self.device.controls[ctrl].is_flagged_write_only:
                cur = str(self.device.controls[ctrl].value)
                self.log.debug(f"{ctrl}: want {value}, have {cur}")
                if not cur.lower() == value.lower():
                    raise DeviceStateError(f"{ctrl} should be {value}, but is {cur}")
            else:
                self.log.debug(f"{ctrl} skipped (not readable)")
        self.log.info("device is configured correctly")
