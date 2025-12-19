# MQTT Topic Reference

This file explains the MQTT topic patterns used by the openWB integration. Use this guide to understand which topics to bridge `in` (to read data from openWB) and `out` (to send commands to openWB) in your MQTT broker.

### Placeholders
*   `{mqttRoot}`: The root topic configured in your integration (e.g., `openWB`).
*   `{deviceID}`: The numeric ID of the device you are configuring.
*   `{charge_template_id}`: The ID of the active charge template for the connected vehicle.
*   `{vehicleID}`: The ID of the connected vehicle.

---

## Controller

### SENSORS_CONTROLLER
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/{key}`
*   **Keys**:
    *   `system/ip_address`
    *   `system/version`
    *   `system/lastlivevaluesJson`
    *   `vehicle/{vehicle_id}/name` (subscribes to multiple vehicle names from id 0-10)

---

## Chargepoint

### SENSORS_PER_CHARGEPOINT
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/chargepoint/{deviceID}/{key}`
*   **Keys**:
    *   `get/currents`
    *   `get/daily_imported`
    *   `get/daily_exported`
    *   `get/evse_current`
    *   `get/exported`
    *   `get/fault_str`
    *   `get/imported`
    *   `get/phases_in_use`
    *   `get/power`
    *   `get/state_str`
    *   `get/voltages`
    *   `get/power_factors`
    *   `get/powers`
    *   `get/frequency`
    *   `config`
    *   `get/connected_vehicle/info`
    *   `get/connected_vehicle/config`
    *   `get/connected_vehicle/soc`
    *   `get/rfid`
    *   `get/vehicle_id`

### BINARY_SENSORS_PER_CHARGEPOINT
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/chargepoint/{deviceID}/{key}`
*   **Keys**:
    *   `plug_state`
    *   `charge_state`
    *   `fault_state`

### LOCKS_PER_CHARGEPOINT
*   **`key`**: `manual_lock`
    *   **IN (Value Topic)**: `{mqttRoot}/chargepoint/{deviceID}/set/manual_lock`
    *   **OUT (Command Topic)**: `{mqttRoot}/set/chargepoint/{deviceID}/set/manual_lock`

### SELECTS_PER_CHARGEPOINT
*   **`key`**: `instant_charging_limitation`
    *   **IN (Value Topic Template)**: `{mqttRoot}/vehicle/template/charge_template/{charge_template_id}` (extracts from JSON)
    *   **OUT (Command Topic Template)**: `{mqttRoot}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/selected`
*   **`key`**: `chargemode`
    *   **IN (Value Topic)**: `{mqttRoot}/chargepoint/{deviceID}/get/connected_vehicle/config` (extracts from JSON)
    *   **OUT (Command Topic Template)**: `{mqttRoot}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/selected`
*   **`key`**: `connected_vehicle`
    *   **IN (Value Topic)**: `{mqttRoot}/chargepoint/{deviceID}/get/connected_vehicle/info` (extracts from JSON)
    *   **OUT (Command Topic)**: `{mqttRoot}/set/chargepoint/{deviceID}/config/ev`

### NUMBERS_PER_CHARGEPOINT
*   **`key`**: `manual_soc`
    *   **IN (Value Topic)**: `{mqttRoot}/chargepoint/{deviceID}/get/connected_vehicle/soc` (extracts from JSON)
    *   **OUT (Command Topic Template)**: `{mqttRoot}/set/vehicle/{vehicleID}/soc_module/calculated_soc_state/manual_soc`
*   **`key`**: `instant_charging_current_control`
    *   **IN (Value Topic Template)**: `{mqttRoot}/vehicle/template/charge_template/{charge_template_id}` (extracts from JSON)
    *   **OUT (Command Topic Template)**: `{mqttRoot}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/current`
*   **`key`**: `pv_charging_min_current_control`
    *   **IN (Value Topic Template)**: `{mqttRoot}/vehicle/template/charge_template/{charge_template_id}` (extracts from JSON)
    *   **OUT (Command Topic Template)**: `{mqttRoot}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/pv_charging/min_current`
*   **`key`**: `instant_charging_energy_limit_control`
    *   **IN (Value Topic Template)**: `{mqttRoot}/vehicle/template/charge_template/{charge_template_id}` (extracts from JSON)
    *   **OUT (Command Topic Template)**: `{mqttRoot}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/amount`
*   **`key`**: `instant_charging_soc_limit_control`
    *   **IN (Value Topic Template)**: `{mqttRoot}/vehicle/template/charge_template/{charge_template_id}` (extracts from JSON)
    *   **OUT (Command Topic Template)**: `{mqttRoot}/set/vehicle/template/charge_template/{charge_template_id}/chargemode/instant_charging/limit/soc`
*   **`key`**: `price_based_charging_max_price`
    *   **IN (Value Topic Template)**: `{mqttRoot}/vehicle/template/charge_template/{charge_template_id}` (extracts from JSON)
    *   **OUT (Command Topic Template)**: `{mqttRoot}/set/vehicle/template/charge_template/{charge_template_id}/et/max_price`

---

## Counter

### SENSORS_PER_COUNTER
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/counter/{deviceID}/{key}`
*   **Keys**:
    *   `voltages`
    *   `power_factors`
    *   `powers`
    *   `frequency`
    *   `currents`
    *   `power`
    *   `fault_str`
    *   `exported`
    *   `imported`
    *   `daily_imported`
    *   `daily_exported`

### BINARY_SENSORS_PER_COUNTER
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/counter/{deviceID}/{key}`
*   **Keys**:
    *   `fault_state`

---

## Battery

### SENSORS_PER_BATTERY
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/bat/{deviceID}/{key}`
*   **Keys**:
    *   `soc`
    *   `power`
    *   `fault_str`
    *   `exported`
    *   `imported`
    *   `daily_imported`
    *   `daily_exported`

### BINARY_SENSORS_PER_BATTERY
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/bat/{deviceID}/{key}`
*   **Keys**:
    *   `fault_state`

---

## PV Generator

### SENSORS_PER_PVGENERATOR
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/pv/{deviceID}/{key}`
*   **Keys**:
    *   `daily_exported`
    *   `monthly_exported`
    *   `yearly_exported`
    *   `exported`
    *   `power`
    *   `currents`
    *   `fault_str`

### BINARY_SENSORS_PER_PVGENERATOR
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/pv/{deviceID}/{key}`
*   **Keys**:
    *   `fault_state`

---

## Vehicle

### SENSORS_PER_VEHICLE
*   **Direction**: `in`
*   **Topic Path 1**: `{mqttRoot}/vehicle/{deviceID}/{key}`
    *   **Key**: `name`
*   **Topic Path 2**: `{mqttRoot}/vehicle/{deviceID}/get/{key}`
    *   **Keys**:
        *   `soc`
        *   `range`
        *   `soc_timestamp`
        *   `fault_str`

### BINARY_SENSORS_PER_VEHICLE
*   **Direction**: `in`
*   **Topic Path**: `{mqttRoot}/vehicle/{deviceID}/get/{key}`
*   **Keys**:
    *   `fault_state`
