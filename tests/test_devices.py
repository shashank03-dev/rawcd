import json
from subprocess import CompletedProcess

from rawcd.devices import OpticalDriveScanner


class FakeRunner:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> CompletedProcess[str]:
        self.commands.append(command)
        return CompletedProcess(command, 0, stdout=json.dumps(self.payload), stderr="")


def test_scanner_parses_usb_optical_drive_with_mountpoint() -> None:
    runner = FakeRunner(
        {
            "blockdevices": [
                {
                    "name": "sda",
                    "type": "disk",
                    "model": "SSD",
                    "tran": "sata",
                    "mountpoints": [None],
                },
                {
                    "name": "sr0",
                    "type": "rom",
                    "model": "USB DVD RW",
                    "tran": "usb",
                    "mountpoints": ["/media/user/HOME_MOVIES"],
                },
            ]
        }
    )

    devices = OpticalDriveScanner(runner=runner).scan()

    assert len(devices) == 1
    assert devices[0].device_path == "/dev/sr0"
    assert devices[0].model == "USB DVD RW"
    assert devices[0].mount_path == "/media/user/HOME_MOVIES"
    assert devices[0].is_usb is True
    assert devices[0].has_media is True
    assert runner.commands == [
        ["lsblk", "-J", "-o", "NAME,TYPE,MODEL,TRAN,MOUNTPOINTS"]
    ]
