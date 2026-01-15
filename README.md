# openWB Integration for Home Assistant

## What's New (December 2025): API Support
This integration now supports connecting to openWB via the new HTTP API, which is the recommended method for most users. The classic MQTT method is still supported for advanced use cases.

For a video overview of the new API setup and how to migrate, click below:

[![Watch the video](https://img.youtube.com/vi/7lbCmwPlw7s/hqdefault.jpg)](https://www.youtube.com/embed/7lbCmwPlw7s)

This custom component integrates your [openWB](https://openwb.de) wallbox (software version 2.x) with Home Assistant. It allows you to monitor and control your charging setup directly from your Home Assistant dashboard.

There are two ways to connect this integration to your openWB:
1.  **API (HTTP):** The new, recommended method for a simple and straightforward setup.
2.  **MQTT:** The classic method, for advanced users or those with specific needs for direct MQTT access.

---

## 1. Which Method Should I Choose?

For most users, the **API method is recommended**.

| Method | Pros | Cons | Best for... |
| :--- | :--- | :--- | :--- |
| **API (HTTP)** | **Simple setup** via the Home Assistant UI. | Data is updated every 15 seconds (polling). | New users and anyone looking for a quick and easy setup. |
| **MQTT** | **Instantaneous updates** via push. | **Complex setup** requiring manual MQTT broker configuration. | Advanced users, those with existing MQTT infrastructure, or those who need to debug using MQTT topics. |

---

## 2. Installation

1.  **Install via HACS (Recommended):**
    *   Make sure you have [HACS](https://github.com/hacs/integration) installed.
    *   Go to HACS > Integrations.
    *   Add this repository as a custom repository.
    *   Search for "openWB2" and install the integration.

2.  **Manual Installation:**
    *   Copy the `custom_components/openwb2mqtt` folder into your Home Assistant `custom_components` directory.

After installation, **restart Home Assistant**.

---

## 3. Configuration Guides

### 3.1 API (HTTP) Configuration (Recommended)

Follow these steps for the simplest way to connect your openWB. This method uses the openWB SimpleAPI, which is documented [here](https://wiki.openwb.de/doku.php?id=openwb:vc:2.1.9:simpleapi#openwb_simpleapi_http).

#### Step 1: Add the Integration
*   In Home Assistant, go to **Settings > Devices & Services**.
*   Click **Add Integration** and search for `openWB`.

#### Step 2: Initial Setup
A configuration window will appear.

1.  **Communication Method:** Select **HTTP API**.
2.  **URL:** Enter the URL for your openWB, replacing the placeholder with its IP address (e.g., `http://192.168.1.123/openWB/simpleAPI.php`).
3.  **Device Type:** Choose the device you want to add (e.g., `Chargepoint`, `Counter`, `PV Generator`).
4.  **Device ID:** Enter the numeric ID for your device. You can find this on the openWB status page.
    *   *How to find the Device ID:*
        ![openWB Status Page with Device IDs](https://github.com/a529987659852/openwb2mqtt/blob/main/openWBStatusTab-IDs.png)
5.  **API Prefix:**
    *   **For new installations:** You can leave this as the default (`openWB`).
    *   **If migrating from MQTT:** To keep your sensor history, you **must** set this to your previous MQTT Root Topic.

#### Step 3: Charge Point Options (if applicable)
If you are adding a Charge Point, you will see an additional screen:

1.  **Wallbox Power:** Select `11 kW` or `22 kW` to match your hardware. This sets the correct maximum values for current control sliders.
2.  **Vehicles:** Define the vehicles you want to select in Home Assistant.
    *   **Format:** `id1=Name1,id2=Name2,...` (e.g., `0=My EV,1=Guest Car`).
    *   The vehicle ID can be found on the openWB status page.
    *   The **Name** must **exactly** match the vehicle name configured in openWB.

#### Step 4: Finalize
Give your new device a name and assign it to an area in Home Assistant. You're all set!

---

### 3.2 MQTT Configuration (Advanced)

This method requires manual configuration of an MQTT broker.

#### Prerequisite: MQTT Broker Bridge Setup
This integration needs to receive data from the openWB's internal MQTT broker. If you use a central MQTT broker in Home Assistant (e.g., the Mosquitto addon), you must create a "bridge" to subscribe to the openWB's topics.

*How to find the MQTT Root Topic:*
The following image shows an example of the MQTT topics published by openWB and how to identify the root topic (e.g., `openWB`).
<img width="1080" alt="HowToConfigureChargePoint-MQTT" src="https://github.com/a529987659852/openwbmqtt/assets/69649604/6ae4c107-e88a-4155-b8ef-d947f819d716">

1.  In your Mosquitto broker's configuration folder, create a new file (e.g., `openwb.conf`).
2.  Add the bridge configuration. Use the `mosquittoExampleConfiguration.conf` file in this repository as a template. You will need to:
    *   Change the `address` to your openWB's IP address.
    *   Update the `topic` lines to match the `Device ID` of the devices you want to integrate.
    *   Use `in` for topics you want to read from openWB and `out` for topics you want to send commands to.

**Example `openwb.conf` snippet:**
```
connection openwb2
address 192.168.1.123:1883
topic openWB/chargepoint/1/# in
topic openWB/set/chargepoint/1/# out
```
3.  Restart your MQTT broker.

#### Step 1: Add the Integration
*   In Home Assistant, go to **Settings > Devices & Services**.
*   Click **Add Integration** and search for `openWB`.

#### Step 2: Configuration
1.  **Communication Method:** Select **MQTT**.
2.  **MQTT Root Topic:** Enter the root topic you identified above (e.g., `openWB`).
3.  **Device Type:** Choose the device you want to add.
4.  **Device ID:** Enter the numeric ID for your device. You can find this on the openWB status page.
    *   *How to find the Device ID:*
        ![openWB Status Page with Device IDs](https://github.com/a529987659852/openwb2mqtt/blob/main/openWBStatusTab-IDs.png)

---

## 4. Migrating from MQTT to API

If you previously used the MQTT method, you can switch to the simpler API method and keep your sensor history by following these steps:

1.  **Check your old settings:** Note your current **MQTT Root Topic** (e.g., `openWB`).
2.  **Delete the old integration:** In Home Assistant, go to the openWB integration for the device you want to migrate and delete it.
3.  **Add a new integration:** Add the openWB integration again.
4.  **Select API:** Choose **HTTP API** as the communication method.
5.  **IMPORTANT - Set API Prefix:** In the configuration, set the **API Prefix** field to the **exact same value** as your old MQTT Root Topic from step 1.
6.  **Complete setup:** Finish the configuration as described in the API guide above.

By matching the API Prefix to the old MQTT Root Topic, the entity IDs will remain the same, and Home Assistant will continue to log data to the existing history.

---

## 5. Provided Devices & Entities

This integration can create the following device types in Home Assistant:

*   **Charge Point:** Represents a charging port on your openWB.
    *   **Sensors:** Power, current, energy, plug state, etc.
    *   **Controls:** Charge mode, target SoC, vehicle selection, etc.
*   **Counter:** Represents a power meter (e.g., your grid connection point).
    *   **Sensors:** Power (total and per phase), current, voltage, imported/exported energy.
*   **Battery:** Represents a home battery storage system.
    *   **Sensors:** Power, state of charge, total charged/discharged energy.
*   **PV Generator:** Represents a solar PV array.
    *   **Sensors:** Power, current, daily/monthly/yearly energy production.
*   **Vehicle:** Represents a vehicle configured in openWB.
    *   **Sensors:** State of charge (SoC), range, and last update timestamp.
*   **Controller:** Represents the central openWB unit.
    *   **Sensors:** Total house consumption, total PV, total charging power, etc.

---

## 6. Troubleshooting & FAQ

*   **API: I don't get any values.**
    *   Maybe your openWB is not on the right version. The API came with 2.1.9. Try this url (remember to adapt the IP) in the web browser or Postman `http://<IP to your wallbox>/openWB/simpleAPI/simpleapi.php/?get_chargepoint_all`.
        If you don't get information about your chargepoint, you don't have the API yet.
    *   Maybe you have changed the API url during configuration. Make sure that you only change the IP.

*   **API: My sensor values only update every 15 seconds.**
    *   This is expected behavior. The API method polls the openWB for new data every 15 seconds.

*   **API: When I switch to another vehicle in Home Assistant, the dropdown in Home Assistant looks strange or doesn't update immediately.**
    *   This is a known cosmetic issue. The integration sends the command to openWB correctly, and the change is applied there. The UI in Home Assistant will correct itself on the next data poll. This happens because the UI displays names, but the integration works with numeric IDs internally.

*   **MQTT: I can see sensor values, but my controls (e.g., changing charge mode) don't work.**
    *   This can be an issue with your MQTT bridge configuration (missing `out` topics).
    *   **Important Note:** Since openWB version 2.1.8, setting values via the standard MQTT topics is often no longer supported since the topic structure changed significantly. This was a primary reason for creating the API method. If you need to control your wallbox, using the API method is strongly recommended.

*   **How do I find the MQTT topics for a specific entity?**
    *   For advanced debugging with MQTT, you can map topics to entities. Check the `MQTT_Topic_Reference.md` file in this repository. For a given entry, like `SENSORS_PER_CHARGEPOINT` with `key="get/power"`, the topic will be `{mqttRoot}/chargepoint/{deviceID}/get/power`. You can then find the corresponding entity by looking for the same `key` in the `const.py` file.
