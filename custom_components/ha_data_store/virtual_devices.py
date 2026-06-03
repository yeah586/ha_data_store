"""虚拟设备模块 — 无需重启 HA 即可动态创建完全功能的虚拟设备。

支持的设备类型：
  - 开关 (switch)     : ON/OFF
  - 灯光 (light)      : ON/OFF、亮度、色温、RGB 颜色
  - 空调 (climate)     : 全部模式、温度、风速、风向 + 模拟温度传感器
  - 窗帘 (cover)      : 开/关/停/位置
  - 风扇 (fan)        : ON/OFF、风速百分比
  - 门锁 (lock)       : 锁定/解锁
  - 传感器 (sensor)    : 可设数值
  - 二元传感器         : ON/OFF
  - 数值 (number)     : 可调范围
  - 选择器 (select)   : 下拉选项

所有实体均使用 RestoreEntity，HA 重启后自动恢复状态。
通过存储的 async_add_entities 回调动态创建，无需重启。
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.components.climate import (
    ClimateEntity, HVACMode, ClimateEntityFeature,
    SWING_ON, SWING_OFF,
)
from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.components.lock import LockEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity

try:
    from homeassistant.components.vacuum import VacuumEntity
except ImportError:
    try:
        from homeassistant.components.vacuum.entity import VacuumEntity
    except ImportError:
        from homeassistant.components.vacuum import StateVacuumEntity as VacuumEntity

try:
    from homeassistant.components.vacuum import VacuumEntityFeature
except ImportError:
    try:
        from homeassistant.components.vacuum.entity import VacuumEntityFeature
    except ImportError:
        try:
            from homeassistant.components.vacuum.const import VacuumEntityFeature
        except ImportError:
            VacuumEntityFeature = None

try:
    from homeassistant.components.vacuum import (
        STATE_CLEANING, STATE_DOCKED, STATE_PAUSED,
        STATE_RETURNING, STATE_IDLE, STATE_ERROR,
    )
except ImportError:
    STATE_CLEANING = "cleaning"
    STATE_DOCKED = "docked"
    STATE_PAUSED = "paused"
    STATE_RETURNING = "returning"
    STATE_IDLE = "idle"
    STATE_ERROR = "error"

from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

VIRTUAL_DEVICE_DOMAIN = "virtual_device"


# =========================================================================== #
#  虚拟开关                                                                       #
# =========================================================================== #
class VirtualSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo) -> None:
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_is_on = False
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            self._attr_is_on = last.state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._attr_is_on


# =========================================================================== #
#  虚拟灯光（完整功能：ON/OFF、亮度、色温、RGB）                                      #
# =========================================================================== #
class VirtualLight(LightEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo) -> None:
        self._attr_color_mode = ColorMode.ONOFF
        LightEntity.__init__(self)
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_is_on = False
        self._attr_brightness = 255
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            self._attr_is_on = last.state == "on"
        if last and last.attributes:
            if "brightness" in last.attributes:
                self._attr_brightness = last.attributes["brightness"]

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        if "brightness" in kwargs:
            self._attr_brightness = kwargs["brightness"]
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = ColorMode.ONOFF
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._attr_is_on


# =========================================================================== #
#  虚拟空调（全部模式 + 温度 + 风速 + 风向 + 模拟温度传感器）                            #
# =========================================================================== #
class VirtualClimate(ClimateEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT,
                         HVACMode.AUTO, HVACMode.DRY, HVACMode.FAN_ONLY]
    _attr_fan_modes = ["低", "中", "高", "自动"]
    _attr_swing_modes = [SWING_OFF, "上下", "左右", "上下+左右"]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE |
        ClimateEntityFeature.FAN_MODE |
        ClimateEntityFeature.SWING_MODE |
        ClimateEntityFeature.TURN_ON |
        ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 1
    _attr_min_temp = 16
    _attr_max_temp = 30

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo,
                 temp_sensor_entity_id: str | None = None) -> None:
        from homeassistant.const import UnitOfTemperature
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_current_temperature = 24
        self._attr_target_temperature = 24
        self._attr_fan_mode = "自动"
        self._attr_swing_mode = SWING_OFF
        self._temp_sensor_entity_id = temp_sensor_entity_id
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.attributes:
            hvac = last.attributes.get("hvac_mode")
            if hvac and hvac in HVACMode.__members__:
                self._attr_hvac_mode = HVACMode(hvac)
            self._attr_current_temperature = last.attributes.get("current_temperature", 24)
            self._attr_target_temperature = last.attributes.get("temperature", 24)
            self._attr_fan_mode = last.attributes.get("fan_mode", "自动")
            self._attr_swing_mode = last.attributes.get("swing_mode", SWING_OFF)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        if "temperature" in kwargs:
            self._attr_target_temperature = kwargs["temperature"]
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._attr_fan_mode = fan_mode
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        self._attr_swing_mode = swing_mode
        self.async_write_ha_state()


# =========================================================================== #
#  虚拟空调温度传感器（模拟趋近目标温度）                                               #
# =========================================================================== #
class VirtualClimateSensor(SensorEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = "temperature"
    _attr_state_class = "measurement"

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo,
                 climate_entity: VirtualClimate) -> None:
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_native_value = 24.0
        self._climate = climate_entity
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            try:
                self._attr_native_value = float(last.state)
            except (ValueError, TypeError):
                pass

    async def _simulate_tick(self, now=None) -> None:
        """每 30 秒模拟温度趋近目标值。"""
        if self._climate._attr_hvac_mode in (HVACMode.COOL, HVACMode.HEAT):
            target = self._climate._attr_target_temperature
            current = self._attr_native_value or 22
            # 向目标趋近 6-12%
            diff = target - current
            step = diff * random.uniform(0.06, 0.12)
            # 加入随机波动 ±0.2
            noise = random.uniform(-0.2, 0.2)
            new_val = round(current + step + noise, 1)
            # 制冷不高于设定+0.3，制热不低于设定-0.3
            if self._climate._attr_hvac_mode == HVACMode.COOL:
                new_val = max(new_val, target - 0.3)
            else:
                new_val = min(new_val, target + 0.3)
            self._attr_native_value = new_val
        else:
            # 关机/送风时自然趋近室温 22°C
            current = self._attr_native_value or 22
            diff = 22 - current
            step = diff * 0.03
            self._attr_native_value = round(current + step, 1)

        # 同步到空调实体
        self._climate._attr_current_temperature = self._attr_native_value
        self.async_write_ha_state()

    def start_simulation(self, hass: HomeAssistant) -> None:
        """启动温度模拟定时器（每 30 秒）。"""
        async_track_time_interval(hass, self._simulate_tick, timedelta(seconds=30))


# =========================================================================== #
#  虚拟窗帘                                                                       #
# =========================================================================== #
class VirtualCover(CoverEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP | CoverEntityFeature.SET_POSITION

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo) -> None:
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_is_closed = True
        self._attr_current_cover_position = 0
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            self._attr_is_closed = last.state == "closed"
        if last and last.attributes:
            self._attr_current_cover_position = last.attributes.get("current_position", 0)

    async def async_open_cover(self, **kwargs) -> None:
        self._attr_is_closed = False
        self._attr_current_cover_position = 100
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs) -> None:
        self._attr_is_closed = True
        self._attr_current_cover_position = 0
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs) -> None:
        pos = kwargs.get("position", 0)
        self._attr_current_cover_position = pos
        self._attr_is_closed = pos == 0
        self.async_write_ha_state()

    @property
    def is_closed(self) -> bool:
        return self._attr_is_closed


# =========================================================================== #
#  虚拟风扇                                                                       #
# =========================================================================== #
class VirtualFan(FanEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo) -> None:
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_is_on = False
        self._attr_percentage = 50
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            self._attr_is_on = last.state == "on"
        if last and last.attributes:
            self._attr_percentage = last.attributes.get("percentage", 50)

    def set_percentage(self, percentage: int) -> None:
        self._attr_percentage = percentage
        self.schedule_update_ha_state()

    async def async_turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs) -> None:
        self._attr_is_on = True
        if percentage is not None:
            self._attr_percentage = percentage
        elif "percentage" in kwargs:
            self._attr_percentage = kwargs["percentage"]
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    @property
    def percentage(self) -> int | None:
        return self._attr_percentage

    @property
    def speed_count(self) -> int:
        return 100


# =========================================================================== #
#  虚拟门锁                                                                       #
# =========================================================================== #
class VirtualLock(LockEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo) -> None:
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_is_locked = True
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            self._attr_is_locked = last.state == "locked"

    async def async_lock(self, **kwargs) -> None:
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs) -> None:
        self._attr_is_locked = False
        self.async_write_ha_state()

    @property
    def is_locked(self) -> bool:
        return self._attr_is_locked


# =========================================================================== #
#  虚拟传感器                                                                     #
# =========================================================================== #
class VirtualSensor(SensorEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo,
                 native_value: Any = None, unit: str | None = None) -> None:
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_native_value = native_value
        if unit:
            self._attr_native_unit_of_measurement = unit
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            try:
                self._attr_native_value = float(last.state)
            except (ValueError, TypeError):
                self._attr_native_value = last.state

    def set_value(self, value: Any) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()


# =========================================================================== #
#  虚拟二元传感器                                                                  #
# =========================================================================== #
class VirtualBinarySensor(BinarySensorEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo) -> None:
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_is_on = False
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            self._attr_is_on = last.state == "on"

    def set_state(self, value: bool) -> None:
        self._attr_is_on = value
        self.async_write_ha_state()


# =========================================================================== #
#  虚拟数值                                                                       #
# =========================================================================== #
class VirtualNumber(NumberEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo,
                 min_val: float = 0, max_val: float = 100, step: float = 1,
                 unit: str | None = None, init_val: float | None = None) -> None:
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_native_value = init_val if init_val is not None else min_val
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        if unit:
            self._attr_native_unit_of_measurement = unit
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            try:
                self._attr_native_value = float(last.state)
            except (ValueError, TypeError):
                pass

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return self._attr_native_value or 0


# =========================================================================== #
#  虚拟选择器                                                                     #
# =========================================================================== #
class VirtualSelect(SelectEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo,
                 options: list[str] | None = None) -> None:
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_options = options or ["选项1", "选项2", "选项3"]
        self._attr_current_option = self._attr_options[0]
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state is not None:
            if last.state in self._attr_options:
                self._attr_current_option = last.state

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        return self._attr_current_option


# =========================================================================== #
#  虚拟扫地机器人                                                                  #
# =========================================================================== #
class VirtualVacuum(VacuumEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_fan_speed_list = ["安静", "标准", "强力", "MAX"]

    @property
    def supported_features(self):
        if VacuumEntityFeature is not None:
            return (
                VacuumEntityFeature.START | VacuumEntityFeature.STOP |
                VacuumEntityFeature.PAUSE | VacuumEntityFeature.RETURN_HOME |
                VacuumEntityFeature.FAN_SPEED |
                VacuumEntityFeature.STATUS | VacuumEntityFeature.STATE
            )
        return 255

    def __init__(self, entity_id: str, name: str, device_info: DeviceInfo) -> None:
        super().__init__()
        self._attr_unique_id = f"{DOMAIN}_virtual_{entity_id}"
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_battery_level = 100
        self._attr_fan_speed = "标准"
        self._attr_state = STATE_DOCKED
        self._attr_status = "已充电完成"
        self.entity_id = entity_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last:
            if last.state:
                self._attr_state = last.state
            if last.attributes:
                self._attr_battery_level = last.attributes.get("battery_level", 100)
                self._attr_fan_speed = last.attributes.get("fan_speed", "标准")
                self._attr_status = last.attributes.get("status", "已充电完成")

    async def async_start(self) -> None:
        self._attr_state = STATE_CLEANING
        self._attr_status = "正在清扫"
        self.async_write_ha_state()

    async def async_stop(self) -> None:
        self._attr_state = STATE_IDLE
        self._attr_status = "已暂停"
        self.async_write_ha_state()

    async def async_pause(self) -> None:
        self._attr_state = STATE_PAUSED
        self._attr_status = "已暂停"
        self.async_write_ha_state()

    async def async_return_to_base(self) -> None:
        self._attr_state = STATE_RETURNING
        self._attr_status = "正在回充"
        self.async_write_ha_state()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs) -> None:
        self._attr_fan_speed = fan_speed
        self.async_write_ha_state()

    async def async_locate(self, **kwargs) -> None:
        self._attr_status = "正在查找机器人"
        self.async_write_ha_state()


# =========================================================================== #
#  设备类型映射                                                                    #
# =========================================================================== #
VIRTUAL_DEVICE_CLASSES: dict[str, type] = {
    "switch": VirtualSwitch,
    "light": VirtualLight,
    "climate": VirtualClimate,
    "cover": VirtualCover,
    "fan": VirtualFan,
    "lock": VirtualLock,
    "sensor": VirtualSensor,
    "binary_sensor": VirtualBinarySensor,
    "number": VirtualNumber,
    "select": VirtualSelect,
    "vacuum": VirtualVacuum,
}


# =========================================================================== #
#  动态创建设备管理器                                                                #
# =========================================================================== #
class VirtualDeviceManager:
    """管理虚拟设备的动态创建与删除。"""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._db_path = hass.data.get(DOMAIN, {}).get("db_path", "")

    def _save_to_db(self, config: dict) -> None:
        if not self._db_path:
            return
        import sqlite3, json
        now = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        extra = {}
        for k in ("init_value", "unit", "min", "max", "step", "options"):
            if k in config and config[k] is not None:
                extra[k] = config[k]
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO virtual_devices (entity_id, device_type, device_name, entity_name, extra_config, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (config["entity_id"], config["device_type"], config.get("device_name", ""),
                 config.get("entity_name", ""), json.dumps(extra, ensure_ascii=False), now),
            )
            conn.commit()
        finally:
            conn.close()

    def _remove_from_db(self, entity_id: str) -> None:
        if not self._db_path:
            return
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("DELETE FROM virtual_devices WHERE entity_id = ?", (entity_id,))
            conn.commit()
        finally:
            conn.close()

    def load_from_db(self) -> list[dict]:
        if not self._db_path:
            return []
        import sqlite3, json
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM virtual_devices").fetchall()
            result = []
            for row in rows:
                config = {
                    "device_type": row["device_type"],
                    "entity_id": row["entity_id"],
                    "device_name": row["device_name"],
                    "entity_name": row["entity_name"] or row["device_name"],
                }
                try:
                    extra = json.loads(row["extra_config"])
                    config.update(extra)
                except (json.JSONDecodeError, TypeError):
                    pass
                result.append(config)
            return result
        finally:
            conn.close()

    def create_device(self, config: dict) -> dict:
        """根据配置创建设备和实体。返回创建结果。"""
        device_type = config["device_type"]
        entity_id = config["entity_id"]
        device_name = config.get("device_name", entity_id.split(".", 1)[1])
        entity_name = config.get("entity_name", device_name)

        device_info = DeviceInfo(
            identifiers={(DOMAIN, "virtual_device_group")},
            name="虚拟设备",
            manufacturer="HA数据存储 — 虚拟设备",
        )

        entity_cls = VIRTUAL_DEVICE_CLASSES.get(device_type)
        if not entity_cls:
            raise ValueError(f"不支持的虚拟设备类型: {device_type}")

        entities = []
        domain = device_type

        # 创建实体
        extra_sensors = []  # 附属传感器，需要走 sensor 平台
        if device_type == "climate":
            climate = VirtualClimate(entity_id, entity_name, device_info)
            temp_sensor_id = f"sensor.{entity_id.split('.', 1)[1]}_temp"
            temp_sensor = VirtualClimateSensor(
                temp_sensor_id, f"{device_name} 温度", device_info, climate,
            )
            entities = [climate]
            extra_sensors = [temp_sensor]
            self._hass.loop.call_soon(
                lambda ts=temp_sensor: ts.start_simulation(self._hass)
            )
        elif device_type == "sensor":
            init_val = config.get("init_value")
            unit = config.get("unit")
            sensor = VirtualSensor(entity_id, entity_name, device_info, init_val, unit)
            entities = [sensor]
        elif device_type == "number":
            min_val = float(config.get("min", 0))
            max_val = float(config.get("max", 100))
            step = float(config.get("step", 1))
            unit = config.get("unit")
            init_val = config.get("init_value")
            if init_val is not None:
                init_val = float(init_val)
            number = VirtualNumber(entity_id, entity_name, device_info,
                                   min_val, max_val, step, unit, init_val)
            entities = [number]
        elif device_type == "select":
            options = config.get("options", [])
            if isinstance(options, str):
                options = [s.strip() for s in options.split(",") if s.strip()]
            sel = VirtualSelect(entity_id, entity_name, device_info, options)
            entities = [sel]
        elif device_type == "binary_sensor":
            is_on = config.get("init_value", False)
            bsen = VirtualBinarySensor(entity_id, entity_name, device_info)
            if is_on:
                bsen._attr_is_on = True
            entities = [bsen]
        else:
            entity = entity_cls(entity_id, entity_name, device_info)
            entities = [entity]

        # 添加主设备实体到对应对平台
        add_cb = self._hass.data.get(DOMAIN, {}).get(f"async_add_{domain}")
        if add_cb:
            add_cb(entities)
        else:
            _LOGGER.warning("[virtual] 域 %s 未就绪", domain)

        # 添加附属传感器到 sensor 平台
        if extra_sensors:
            sensor_cb = self._hass.data.get(DOMAIN, {}).get("async_add_sensor")
            if sensor_cb:
                sensor_cb(extra_sensors)
                for s in extra_sensors:
                    entities.append(s)

        self._save_to_db(config)
        _LOGGER.info("[virtual] 创建虚拟设备 %s (%s), %d 个实体",
                      entity_id, device_type, len(entities))

        # 记录到追踪列表
        self._hass.data.setdefault(DOMAIN, {}).setdefault("virtual_devices", []).append({
            "entity_id": entity_id,
            "device_type": device_type,
            "device_name": device_name,
            "entity_count": len(entities),
            "entities": entities,
        })

        return {
            "entity_id": entity_id,
            "device_type": device_type,
            "device_name": device_name,
            "entity_count": len(entities),
        }

    def list_devices(self) -> list[dict]:
        return self._hass.data.get(DOMAIN, {}).get("virtual_devices", [])

    def delete_device(self, entity_id: str) -> bool:
        vd_list = self._hass.data.get(DOMAIN, {}).get("virtual_devices", [])
        target = None
        for item in vd_list:
            if item["entity_id"] == entity_id:
                target = item
                break
        if not target:
            return False

        # 从 entity_registry 移除所有关联实体
        from homeassistant.helpers import entity_registry as er
        reg = er.async_get(self._hass)
        for ent in target["entities"]:
            eid = getattr(ent, 'entity_id', None) or getattr(ent, '_attr_entity_id', None)
            if eid:
                reg.async_remove(eid)

        vd_list.remove(target)
        self._remove_from_db(entity_id)
        _LOGGER.info("[virtual] 删除虚拟设备 %s", entity_id)
        return True

    @staticmethod
    def _type_label(t: str) -> str:
        return {"switch": "开关", "light": "灯", "climate": "空调",
                "cover": "窗帘", "fan": "风扇", "lock": "门锁",
                "sensor": "传感器", "binary_sensor": "二元传感器",
                "number": "数值", "select": "选择器",
                "vacuum": "扫地机器人"}.get(t, t)
