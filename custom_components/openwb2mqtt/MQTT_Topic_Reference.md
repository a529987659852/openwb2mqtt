# MQTT Topic Reference

This page lists every MQTT topic that the integration uses when you connect over **MQTT**.
The integration only uses the **simpleAPI** of openWB (openWB 2.1.9 or newer, simpleAPI revision 2).
The classic `openWB/...` topics (for example `openWB/chargepoint/1/get/power`) are **not** used anymore.

## Placeholders

| Placeholder | Meaning |
|---|---|
| `{root}` | MQTT root topic from the integration setup. Default: `openWB` |
| `{id}` | Device ID in openWB (chargepoint, counter, battery or PV ID) |

Example: with the default root and chargepoint ID 3, the key `power` is read from
`openWB/simpleAPI/chargepoint/3/power`.

## How the integration reads values

- For each configured device, the integration subscribes to
  `{root}/simpleAPI/{type}/{id}/#` (QoS 1). `{type}` is one of
  `chargepoint`, `counter`, `bat` or `pv`.
- The part after `{root}/simpleAPI/{type}/{id}/` is the **key**. The tables below list these keys.
- If a key starts with `get/`, this part is ignored (so `get/power` is the same as `power`).
  Chargepoint topics have no `get/`; counter, bat and pv topics keep `get/`.
- Values with three phases are sent as separate topics, for example
  `currents/1`, `currents/2`, `currents/3`.
- When `config/name` or `version` arrives, the device name or software version
  shown in Home Assistant is updated.

### Chargepoint – `{root}/simpleAPI/chargepoint/{id}/<key>`

| Key | Meaning | Notes |
|---|---|---|
| `power` | Charging power | W |
| `powers/1` … `powers/3` | Power per phase | W |
| `currents/1` … `currents/3` | Current per phase | A |
| `voltages/1` … `voltages/3` | Voltage per phase | V |
| `power_factors/1` … `power_factors/3` | Power factor per phase | |
| `frequency` | Grid frequency | Hz |
| `imported` / `exported` | Total energy charged / discharged | Wh |
| `daily_imported` / `daily_exported` | Energy today | Wh |
| `evse_current` | Current set at the EVSE | A |
| `phases_in_use` | Phases in use | |
| `state_str` | Status text | |
| `fault_str` / `fault_state` | Fault text / fault state | |
| `plug_state` | Vehicle plugged in | true / false |
| `charge_state` | Vehicle is charging | true / false |
| `manual_lock` | Chargepoint manually locked | true / false |
| `chargemode` | Charge mode | instant_charging, pv_charging, eco_charging, scheduled_charging, time_charging, stop, standby (the short names instant, pv, eco, target are write only) |
| `config/name` | Chargepoint name | used as device name |
| `vehicle_id` / `vehicle_name` | Connected vehicle | |
| `soc/soc` / `soc/timestamp` | Vehicle SoC and its time | % |
| `soc/range_charged` | Range charged | km |
| `pro_soc` / `pro_soc_timestamp` | SoC reported by the chargepoint and its time | % |
| `rfid` / `rfid_timestamp` | Last RFID tag and its time | |
| `minimal_permanent_current` | Min. permanent current (PV charging) | A |
| `minimal_pv_soc` | Min. SoC (PV charging) | % |
| `max_price_eco` | Max. price (eco charging) | arrives in ct/kWh, shown in €/kWh |
| `instant_charging_limit` | Limit (instant charging) | none, soc, amount |
| `instant_charging_limit_soc` | SoC limit (instant charging) | % |
| `instant_charging_limit_amount` | Energy limit (instant charging) | kWh |
| `pv_charging_limit` | Limit (PV charging) | none, soc, amount |
| `pv_charging_limit_soc` | SoC limit (PV charging) | % |
| `pv_charging_limit_amount` | Energy limit (PV charging) | kWh |
| `control_parameter/limit/message` | Why the charging power is limited | text, empty (unknown) when no limit is active |
| `control_parameter/limit/limiting_value` | Reason code of the limit | text, empty (unknown) when no limit is active |
| `charging_current` / `charging_power` / `charging_voltage` | Charging values | A / W / V |
| `serial_number` | Serial number | |
| `version` | Software version | used as device version |

Some chargepoint entities (charge template name, instant charging current sensor,
minimum current of the charge mode, manual SoC, connected vehicle select) are only
available with the HTTP API.

### Counter – `{root}/simpleAPI/counter/{id}/<key>`

| Key | Meaning | Notes |
|---|---|---|
| `power` | Power | W |
| `powers/1` … `powers/3` | Power per phase | W |
| `currents/1` … `currents/3` | Current per phase | A |
| `voltages/1` … `voltages/3` | Voltage per phase | V |
| `power_factors/1` … `power_factors/3` | Power factor per phase | |
| `frequency` | Grid frequency | Hz |
| `imported` / `exported` | Total energy imported / exported | Wh |
| `daily_imported` / `daily_exported` | Energy today | Wh |
| `fault_str` / `fault_state` | Fault text / fault state | |

### Battery – `{root}/simpleAPI/bat/{id}/<key>`

| Key | Meaning | Notes |
|---|---|---|
| `soc` | State of charge | % |
| `power` | Power | W |
| `currents/1` … `currents/3` | Current per phase | A |
| `imported` / `exported` | Total energy charged / discharged | Wh |
| `daily_imported` / `daily_exported` | Energy today | Wh |
| `fault_str` / `fault_state` | Fault text / fault state | |

### PV – `{root}/simpleAPI/pv/{id}/<key>`

| Key | Meaning | Notes |
|---|---|---|
| `power` | PV power | W, shown as a positive value |
| `currents/1` … `currents/3` | Current per phase | A |
| `exported` | Total energy produced | Wh |
| `daily_exported` / `monthly_exported` / `yearly_exported` | Energy today / this month / this year | Wh |
| `fault_str` / `fault_state` | Fault text / fault state | |

## How the integration writes values

When you change a number, select or lock entity, the integration publishes the new value to a
`{root}/simpleAPI/set/...` topic (QoS 0, not retained). The payload is plain text.

| Topic | Entity | Payload | Range |
|---|---|---|---|
| `{root}/simpleAPI/set/chargepoint/{id}/chargemode` | Charge mode (select) | `instant`, `pv`, `eco`, `target`, `stop` | – |
| `{root}/simpleAPI/set/chargepoint/{id}/chargecurrent` | Target current, instant charging (number) | Ampere, e.g. `16` | integer A |
| `{root}/simpleAPI/set/chargepoint/{id}/minimal_permanent_current` | Min. permanent current, PV charging (number) | Ampere, e.g. `6` | integer A |
| `{root}/simpleAPI/set/chargepoint/{id}/minimal_pv_soc` | Min. SoC, PV charging (number) | Percent, e.g. `20` | integer % |
| `{root}/simpleAPI/set/chargepoint/{id}/max_price_eco` | Max. price, eco charging (number) | ct/kWh (the entity shows €/kWh) | number |
| `{root}/simpleAPI/set/chargepoint/{id}/chargepoint_lock` | Manual lock (lock) | `true` / `false` | – |
| `{root}/simpleAPI/set/instant_charging_limit` | Limit, instant charging (select) | `none`, `soc`, `amount` | – |
| `{root}/simpleAPI/set/instant_charging_limit_soc` | SoC limit, instant charging (number) | Percent, e.g. `80` | integer 0–100 |
| `{root}/simpleAPI/set/instant_charging_limit_amount` | Energy limit, instant charging (number) | kWh, e.g. `25` | integer 1–50 kWh |
| `{root}/simpleAPI/set/pv_charging_limit` | Limit, PV charging (select) | `none`, `soc`, `amount` | – |
| `{root}/simpleAPI/set/pv_charging_limit_soc` | SoC limit, PV charging (number) | Percent, e.g. `80` | integer 0–100 |
| `{root}/simpleAPI/set/pv_charging_limit_amount` | Energy limit, PV charging (number) | kWh, e.g. `25` | integer 1–50 kWh |
| `{root}/simpleAPI/set/bat_mode` | Battery mode (battery select) | `min_soc_bat_mode`, `ev_mode`, `bat_mode` | – |
| `{root}/simpleAPI/set/bat_power_reserve` | Reserved battery power (battery number) | Watt | integer ≥ 0 W, no upper limit (the Home Assistant slider stops at 10 000) |

Notes:

- Topics without `chargepoint/{id}` act on the chargepoint with the **lowest ID**
  (or on the whole openWB, for `bat_mode` and `bat_power_reserve`).
- Only target current (instant charging), battery mode and reserved battery power have
  no read topic. These entities show the **last value sent** from Home Assistant, not
  the value currently stored in openWB.

## Known behaviour of the simpleAPI daemon

- **Limit setters act on the lowest chargepoint ID:** `set/instant_charging_limit*` and
  `set/pv_charging_limit*` always change the chargepoint with the lowest ID. An ID in the
  topic is ignored. The entities on other chargepoints keep showing their own (unchanged)
  value. The HTTP API uses `chargepoint_nr` and is not affected.
- **Failed chargepoint commands are cleared:** the daemon clears `set/chargepoint/...`
  topics even when the command failed (for example an invalid value, or the charge
  template is not cached yet). For entities without a read topic (target current),
  Home Assistant may show a value that openWB never accepted. Check the daemon log.
- **Failed limit and battery commands stay on their set topic.** Home Assistant publishes
  them non-retained, so they are not repeated. Do not publish them retained by hand.
- **`evse_current` has two sources:** it is fed by `get/evse_current` and `set/current`,
  so "Ladestromvorgabe" can switch between both values.

## Example

Watch all values of chargepoint 3:

```
mosquitto_sub -h <broker> -t "openWB/simpleAPI/chargepoint/3/#" -v
```

Switch chargepoint 3 to PV charging:

```
mosquitto_pub -h <broker> -t "openWB/simpleAPI/set/chargepoint/3/chargemode" -m "pv"
```
