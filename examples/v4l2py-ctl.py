import argparse

from v4l2py.device import Device, MenuControl, LegacyControl


def _get_ctrl(cam, control):
    if control.isdigit() or control.startswith("0x"):
        _ctrl = int(control, 0)
    else:
        _ctrl = control

    try:
        ctrl = cam.controls[_ctrl]
    except KeyError:
        return None
    else:
        return ctrl


def show_control_status(device: str, legacy_controls: bool) -> None:
    with Device(device, legacy_controls=legacy_controls) as cam:
        print("Showing current status of all controls ...\n")
        print(f"*** {cam.info.card} ***")

        for cc in cam.controls.used_classes():
            print(f"\n{cc.name.title()} Controls\n")

            for ctrl in cam.controls.with_class(cc):
                print("0x%08x:" % ctrl.id, ctrl)
                if isinstance(ctrl, MenuControl):
                    for key, value in ctrl.items():
                        print(11 * " ", f" +-- {key}: {value}")
                elif isinstance(ctrl, LegacyControl):
                    for item in ctrl.menu.values():
                        print(11 * " ", f" +-- {item}")
        print("")


def get_controls(device: str, controls: list, legacy_controls: bool) -> None:
    with Device(device, legacy_controls=legacy_controls) as cam:
        print("Showing current value of given controls ...\n")

        for control in controls:
            ctrl = _get_ctrl(cam, control)
            if not ctrl:
                print(f"{control}: unknown control")
                continue

            if not ctrl.is_flagged_write_only:
                print(f"{control} = {ctrl.value}")
            else:
                print(f"{control} is write-only, thus cannot be read")
        print("")


def set_controls(
    device: str, controls: list, legacy_controls: bool, clipping: bool
) -> None:
    controls = (
        (ctrl.strip(), value.strip())
        for (ctrl, value) in (c.split("=") for c in controls)
    )

    with Device(device, legacy_controls=legacy_controls) as cam:
        print("Changing value of given controls ...\n")

        cam.controls.set_clipping(clipping)
        for control, value_new in controls:
            ctrl = _get_ctrl(cam, control)
            if not ctrl:
                print(f"{control}: unknown control")
                continue

            if not ctrl.is_flagged_write_only:
                value_old = ctrl.value
            else:
                value_old = "(write-only)"

            try:
                ctrl.value = value_new
            except Exception as err:
                success = False
                reason = f"{err}"
            else:
                success = True

            result = "%-5s" % ("OK" if success else "ERROR")

            if success:
                print(f"{result} {control}: {value_old} -> {value_new}\n")
            else:
                print(
                    f"{result} {control}: {value_old} -> {value_new}\n{result} {reason}\n"
                )


def reset_controls(device: str, controls: list, legacy_controls: bool) -> None:
    with Device(device, legacy_controls=legacy_controls) as cam:
        print("Resetting given controls to default ...\n")

        for control in controls:
            ctrl = _get_ctrl(cam, control)
            if not ctrl:
                print(f"{control}: unknown control")
                continue

            try:
                ctrl.set_to_default()
            except Exception as err:
                success = False
                reason = f"{err}"
            else:
                success = True

            result = "%-5s" % ("OK" if success else "ERROR")

            if success:
                print(f"{result} {control} reset to {ctrl.default}\n")
            else:
                print(f"{result} {control}:\n{result} {reason}\n")


def reset_all_controls(device: str, legacy_controls: bool) -> None:
    with Device(device, legacy_controls=legacy_controls) as cam:
        print("Resetting all controls to default ...\n")
        cam.controls.set_to_default()


def csv(string: str) -> list:
    return [v.strip() for v in string.split(",")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--legacy",
        default=False,
        action="store_true",
        help="use legacy controls (default: %(default)s)",
    )
    parser.add_argument(
        "--clipping",
        default=False,
        action="store_true",
        help="when changing numeric controls, enforce the written value to be within allowed range (default: %(default)s)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="0",
        metavar="<dev>",
        help="use device <dev> instead of /dev/video0; if <dev> starts with a digit, then /dev/video<dev> is used",
    )
    parser.add_argument(
        "--get-ctrl",
        type=csv,
        default=[],
        metavar="<ctrl>[,<ctrl>...]",
        help="get the values of the specified controls",
    )
    parser.add_argument(
        "--set-ctrl",
        type=csv,
        default=[],
        metavar="<ctrl>=<val>[,<ctrl>=<val>...]",
        help="set the values of the specified controls",
    )
    parser.add_argument(
        "--reset-ctrl",
        type=csv,
        default=[],
        metavar="<ctrl>[,<ctrl>...]",
        help="reset the specified controls to their default values",
    )
    parser.add_argument(
        "--reset-all",
        default=False,
        action="store_true",
        help="reset all controls to their default value",
    )

    args = parser.parse_args()

    if args.device.isdigit():
        dev = f"/dev/video{args.device}"
    else:
        dev = args.device

    if args.reset_all:
        reset_all_controls(dev, args.legacy)
    elif args.reset_ctrl:
        reset_controls(dev, args.reset_ctrl, args.legacy)
    elif args.get_ctrl:
        get_controls(dev, args.get_ctrl, args.legacy)
    elif args.set_ctrl:
        set_controls(dev, args.set_ctrl, args.legacy, args.clipping)
    else:
        show_control_status(dev, args.legacy)

    print("Done.")
