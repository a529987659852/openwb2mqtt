# openWB2 with Home Assistant

This is a custom component for Home Assistant supporting the [openWB](https://openwb.de/main/) wallbox for charging electric vehicles. The integration subscribes to MQTT topics `prefix/<various values>` which are used by openwb to broadcast information and displays this informations as entities. You can also change, for example, the charge mode of a charge point using a dropdown.

Note: I provide this custom integration without any warranty. It lies in the responsability of each user to validate the functionality with his/her own openWB!

This integration assumes that you run the **openWB using software version 2.x**. If your wallbox still uses the version 1.9x, please use the older version of this integration (https://github.com/a529987659852/openwbmqtt).


If you need help, also have a look [here](http://tech-engineering.de/home-assistant-und-openwb). Although created for the previous version of this integration, you should still find useful information if you're not familiar to MQTT and/or custom integrations in Home Assistant.

## What does the custom integration provide in detail?
My integration provides the following device types:

- Wallbox: This device type represents the openWB itself. You get the following sensors:
  - House consumption
  - Total battery power and state of charge
  - Total PV production
  - Total charging power
  - The sensors correspond to what the openWB shows in the upper section on the overview page.
- Charge Point: This device represents a charge point of the openWB. You should be able to configure the internal charge point as well as charge points from remote openWBs.
You get, for example, the following sensors:
  - Charge power (total and individual phases)
  - Number of active phases
  - Current
  - Voltage
  - Selected charge mode
  - Total energy values
  - Plug and charge states
  - And so on...
- Counter: This device represents a counter, for example, the counter that measures your inbound and outbound energy from the supplier. You get, for example, the following sensors:
  -  Power (total and individual phases)
  -  Current
  -  Voltage
  -  Total energy values (imported and exported energy)
  -  And so on...
- Battery: This device represents a battery, for example, a house battery. You get, for example, the following sensors:
  - Power
  - State of charge
  - Total energy values (charged into the battery and taken out of the battery) 

## Example Configuration for openWB2
When setting up this integration, you must choose the device to be created and provide additional details (MQTT root and device ID).

How to find out the device ID and MQTT root?

This image shows an example of the MQTT topics published by openWB2 and how to identify the MQTT root topic
<img width="1080" alt="HowToConfigureChargePoint-MQTT" src="https://github.com/a529987659852/openwbmqtt/assets/69649604/6ae4c107-e88a-4155-b8ef-d947f819d716">

This image shows the openWB2 status page (http://<your-ip>/openWB/web/settings/#/Status) and the device IDs:
![HowToConfigureChargepoint-Status](https://github.com/a529987659852/openwbmqtt/assets/69649604/621be5ee-0a75-44ea-a652-6197ae368f49)


# How to add this custom component to home assistant

## Step 1: Deploy the Integration Coding to HA
### Option 1: Via HACS
Make sure you have [HACS](https://github.com/hacs/integration) installed. Under HACS, choose Integrations. Add this repository as a user-defined repository.

### Option 2: Manually
## Step 1: Clone component
Clone the custom component to your custom components folder.

## Step 2: Restart HA
Restart your HA instance as usual.

## Step 3: Add the Integration
In HA, choose Settings -> Integrations -> Add Integration to add the integration. HA will display a configuration window. For details, see next section. If the integration is not displayed, it may help to refresh your browser cache.

# Configuration of the Integration and Additional Information
The integration subscribes to MQTT topics `prefix/<various values>` which are used by openwb to broadcast information.

The first parameter, **mqttroot**, defines the prefix that shall be applied to all MQTT topics. By default, openWB publishes data to the MQTT topic `openWB/#` (for example `openWB/lp/1/%Soc`). In this case, set the prefix to openWB and the integration will subscribe to MQTT data coming from openWB, for example `openWB/lp/1/%Soc`, or `openWB/global/chargeMode`, and so on.
  
The second parameter, **chargepoints**, is the number of configured charge points. For each charge point, the integration will set up one set of sensors.

# Mosquitto Configuration in an Internal Network

If you're in an internal network, for example your home network, you can simply subscribe the openWB mosquitto server with the mosquitto server you're using with home assistant. No bridge is required. Instead, add the following to the configuration (for example in /etc/mosquitto/conf.d/openwb.conf):

```
#
# bridge to openWB Wallbox
#
connection openwb
address openwb.fritz.box:1883
start_type automatic
topic openWB/# both 2
local_clientid openwb.mosquitto
try_private false
cleansession true
```
If using the mqtt configuration above, **mqttroot** is `openWB` (this is the default value). Don't add a '/'.

If your're publishing the data from the openWB mosquitto server to another MQTT server via a bridge, the topics on the other MQTT server are usually prepended with a prefix. If this is the case, also include this prefix into the first configuration parameter, for example `somePrefix/openWB`. Then, the integration coding will subscribe to MQTT data comfing from MQTT, for example `somePrefix/openWB/global/chargeMode`, or `somePrefix/openWB/lp/1/%Soc`, and so on.
