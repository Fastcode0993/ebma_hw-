"""Headless Bluetooth pairing agent for Raspberry Pi."""
from __future__ import annotations

import logging

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib


BUS_NAME = "org.bluez"
AGENT_INTERFACE = "org.bluez.Agent1"
AGENT_MANAGER_INTERFACE = "org.bluez.AgentManager1"
ADAPTER_INTERFACE = "org.bluez.Adapter1"
DEVICE_INTERFACE = "org.bluez.Device1"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
AGENT_PATH = "/robot/AutoPairAgent"


class AutoPairAgent(dbus.service.Object):
    def __init__(self, bus, path):
        super().__init__(bus, path)
        self.bus = bus

    def trust_device(self, device) -> None:
        try:
            props = dbus.Interface(self.bus.get_object(BUS_NAME, device), PROPERTIES_INTERFACE)
            props.Set(DEVICE_INTERFACE, "Trusted", dbus.Boolean(1))
            logging.info("Trusted device=%s", device)
        except Exception as exc:
            logging.warning("Failed to trust device=%s: %s", device, exc)

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Release(self):
        logging.info("Agent released")

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        logging.info("AuthorizeService device=%s uuid=%s", device, uuid)
        self.trust_device(device)

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        logging.info("RequestPinCode device=%s", device)
        self.trust_device(device)
        return "0000"

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        logging.info("RequestPasskey device=%s", device)
        self.trust_device(device)
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        logging.info("DisplayPasskey device=%s passkey=%06d entered=%d", device, passkey, entered)

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        logging.info("DisplayPinCode device=%s pincode=%s", device, pincode)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        logging.info("Auto-confirm pairing device=%s passkey=%06d", device, passkey)
        self.trust_device(device)

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        logging.info("Auto-authorize device=%s", device)
        self.trust_device(device)

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Cancel(self):
        logging.info("Agent request cancelled")


def find_adapter(bus):
    manager = dbus.Interface(bus.get_object(BUS_NAME, "/"), "org.freedesktop.DBus.ObjectManager")
    objects = manager.GetManagedObjects()
    for path, interfaces in objects.items():
        if ADAPTER_INTERFACE in interfaces:
            return path
    raise RuntimeError("Bluetooth adapter not found")


def set_adapter_property(bus, adapter_path: str, name: str, value) -> None:
    props = dbus.Interface(bus.get_object(BUS_NAME, adapter_path), PROPERTIES_INTERFACE)
    props.Set(ADAPTER_INTERFACE, name, value)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter_path = find_adapter(bus)
    set_adapter_property(bus, adapter_path, "Powered", dbus.Boolean(1))
    set_adapter_property(bus, adapter_path, "Pairable", dbus.Boolean(1))
    set_adapter_property(bus, adapter_path, "DiscoverableTimeout", dbus.UInt32(0))
    set_adapter_property(bus, adapter_path, "Discoverable", dbus.Boolean(1))

    AutoPairAgent(bus, AGENT_PATH)
    manager = dbus.Interface(bus.get_object(BUS_NAME, "/org/bluez"), AGENT_MANAGER_INTERFACE)
    try:
        manager.UnregisterAgent(AGENT_PATH)
    except Exception:
        pass
    manager.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
    manager.RequestDefaultAgent(AGENT_PATH)
    logging.info("Auto pairing agent registered. Adapter=%s", adapter_path)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
