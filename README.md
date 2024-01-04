# openWB2 with Home Assistant

This is a custom component for Home Assistant supporting the [openWB](https://openwb.de/main/) wallbox for charging electric vehicles. The integration subscribes to MQTT topics which are used by openWB to broadcast information and displays this informations as entities. You can also change, for example, the charge mode of a charge point.

Note: I provide this custom integration without any warranty. It lies in the responsability of each user to validate the functionality with his/her own openWB!

This integration assumes that you run the **openWB using software version 2.x**. If your wallbox still uses the version 1.9x, please use the older version of this integration (https://github.com/a529987659852/openwbmqtt).


If you need help, also have a look [here](http://tech-engineering.de/home-assistant-und-openwb). Although created for the previous version of this integration, you should still find useful information if you're not familiar to MQTT and/or custom integrations in Home Assistant.

## What does the custom integration provide?
My integration provides the following device types:

- Wallbox: This device type represents the openWB itself and provides the following sensors:
  - House consumption
  - Total battery power and state of charge
  - Total PV production
  - Total charging power
  - *Note*: The sensors correspond to what the openWB shows in the upper section on the overview page.
 
- Charge Point: This device represents a charge point of the openWB and provides, for example, the following sensors:
  - Charge power (total and individual phases)
  - Number of active phases
  - Current
  - Voltage
  - Selected charge mode
  - Total energy values
  - Plug and charge states
  - And so on...
  - *Note*: You should be able to configure the internal charge point as well as charge points from remote openWBs.
    
- Counter: This device represents a counter, for example, the counter that measures your inbound and outbound energy from the supplier. This device provides, for example, the following sensors:
  -  Power (total and individual phases)
  -  Current
  -  Voltage
  -  Total energy values (imported and exported energy)
  -  And so on...
 
- Battery: This device represents a battery, for example, a house battery and provides, for example, the following sensors:
  - Power
  - State of charge
  - Total energy values (charged into the battery and taken out of the battery)
  - And so on...

- PV Generator: This device represents a PV generator and provides, for example, the following sensors:
  - Power
  - Current
  - Energy values (total, today, month, year)
  - And so on... 

# How to add this custom component to Home Assistant

## Step 1: Deploy the Integration Coding to Home Assistant
### Option 1: Via HACS
Make sure you have [HACS](https://github.com/hacs/integration) installed. Under HACS, choose Integrations. Add this repository as a user-defined repository.

### Option 2: Manually
Clone the custom component to your custom_components folder.

## Step 2: Restart Home Assistant
Restart your HA instance.

## Step 3: Add and Configure the Integration
In HA, choose Settings -> Integrations -> Add Integration to add the integration. HA will display a configuration window. For details, refer to the *Example Configuration* section

# Example Configuration for openWB2
When setting up this integration, you must choose the device type to be created and provide additional details (MQTT root and device ID). 
- The device type corresponds to the list of devices from the previous section.
- The device ID is shown on the Status page of the openWB management webinterface.
- The MQTT root is the header topic which is used by the wallbox to publish all values.

**How to find out the device ID and MQTT root?**

This image shows an example of the MQTT topics published by openWB2 and how to identify the MQTT root topic
<img width="1080" alt="HowToConfigureChargePoint-MQTT" src="https://github.com/a529987659852/openwbmqtt/assets/69649604/6ae4c107-e88a-4155-b8ef-d947f819d716">

This image shows the openWB2 status page (http://your-ip/openWB/web/settings/#/Status) and the device IDs:
![HowToConfigureChargepoint-Status](https://github.com/a529987659852/openwbmqtt/assets/69649604/621be5ee-0a75-44ea-a652-6197ae368f49)


# Additional Information: Mosquitto Configuration in an Internal Network

If you're in an internal network, for example your home network, you can simply subscribe to the internal openWB mosquitto server with the mosquitto server you're using with home assistant. No bridge in openWB (Settings -> System -> MQTT Bridge) is required. Instead, create a bridge from the MQTT server your Home Assistant is connected to to the internal MQTT server in the openBW using the following to the configuration (for example in /etc/mosquitto/conf.d/openwb.conf). 

*Alternatively, you can also use the internal MQTT server in openWB as primary MQTT server in your network and connect Home Assistant to this MQTT server.*

```
#
# bridge to openWB Wallbox
#
connection openwb
address openwb.fritz.box:1883
start_type automatic
topic openWB/# both 2
## Carefull: Using above line, you allow read and write access to all topics.
# You might want to limit write access to certain topics.
local_clientid openwb.mosquitto
try_private false
cleansession true
```
If using the mqtt configuration above, **mqttroot** is `openWB` (this is the default value). Don't add a '/'.

If your're publishing the data from the openWB mosquitto server to another MQTT server via a bridge, the topics on the other MQTT server are usually prepended with a prefix. If this is the case, also include this prefix into the first configuration parameter, for example `somePrefix/openWB`. Then, the integration coding will subscribe to MQTT data comfing from MQTT, for example `somePrefix/openWB/system/ip_address`, or `somePrefix/openWB/chargepoint/4/get/charge_state`, and so on.
