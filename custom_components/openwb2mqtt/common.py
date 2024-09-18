from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, MANUFACTURER, MODEL


class OpenWBBaseEntity:
    """Openwallbox entity base class."""

    deviceID: int | None = None

    def __init__(
        self,
        device_friendly_name: str,
        mqtt_root: str,
    ) -> None:
        """Init device info class."""
        self.device_friendly_name = device_friendly_name
        self.mqtt_root = mqtt_root

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return DeviceInfo(
            name=self.device_friendly_name,
            identifiers={(DOMAIN, self.device_friendly_name, self.mqtt_root)},
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
