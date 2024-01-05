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


# Additional Information: How to get the openWB values in Home Assistant using MQTT

**TLDR**: Use the file *mosquittoExampleConfiguration.conf* contained in this repository to configure your eclipse MQTT server to import data from the openWB MQTT server and to send data to it. Don't forget to change IP address and device ID(s).

From a technical perspective, this integration uses an MQTT server to obtain the data from the wallbox. The wallbox itself has its own MQTT server. Depending on your network setup, you have two options:
- If you don't need MQTT for anything else, you can use the MQTT server of the openWB. In this case, configure the MQTT configuration in your Home Assistant to connect to the MQTT server of the openWB.
- If you need MQTT for other integrations (for example tasmota devices, and so on), you might already run your own MQTT server and have Home Assistant connected to this server. In this case, you must establish a bridge between the server the Home Assistant is connected to (we'll call this one HA-MQTT) and the MQTT server of the openWB (we'll call this one openWB-MQTT).

Let's disuss the second option in more detail.

To establish a bridge, you can either start on the openWB-MQTT and export values to the HA-MQTT. This can be set up in the webinterface of openWB. Go to section Einstellungen -> System -> MQTT-Brücken and make the necessary settings. Since I'm not using this approach, I cannot give you additional hints. 

Alternatively, you can start on the HA-MQTT and subscribe to topics on the openWB-MQTT. To do this, you have to change the configuration file of the MQTT server. I'm using the Mosquitto MQTT server. This is also the server you run if you're using the Home Assistant MQTT addon. To subscribe to other MQTT servers in Mosquitto, navigate to the config folder of Mosquitto, create a sub-directory conf.d (if it does not already exist), and create a file openWB.conf. In the file, you configure your bridge. See the following example:

```
#
# bridge to openWB Wallbox
#
connection openwb2
local_clientid openwb2.mosquitto

#TODO: Replace IP address
address 192.168.0.68:1883

#Sensors Controller
topic openWB/system/ip_address in
topic openWB/system/version in
topic openWB/system/lastlivevaluesJson in

#Sensors per Chargepoint
#TODO: Replace 4 by your chargepoint ID
topic openWB/chargepoint/4/get/# in
topic openWB/chargepoint/4/config in
```

You must change the following:
- In line address, thange the ip 192.168.0.68 to the IP address of the openWB-MQTT server.
- In section "Sensors per Chargepoint", replace the chargepoint ID 4 by the chargepoint ID that you want to add to Home Assistant.

Then save the file and restart Mosquitto. You should now see MQTT topics with values coming from the openWB-MQTT server. 

**Note**: The example configuration is not complete. Please refer to the file mosquittoExampleConfiguration.conf in this repository which contains a fully running example. Just don't forget to adapt the device IDs!

The configuration option 'in' in each topic line takes care that data from the openWB-MQTT server is only imported to the HA-MQTT. Therefore, the select entity in Home Assistant does not work, yet. Let's look into the following section of the example configuration:
```
#Selects per Chargepoint
#TODO: Replace 4 by your chargepoint ID
topic openWB/chargepoint/4/get/connected_vehicle/config in
topic openWB/set/vehicle/template/charge_template/+/chargemode/selected out
```

The last line exports a topic FROM the HA-MQTT server TO the openWB-MQTT server by specifiying the 'out' option. This topic is populated by Home Assistant when you change the Chargemode on the UI, for example from PV Charging (PV-Laden) to Instant Charging (Sofortladen).

# Additional Information: Which MQTT topics refer to which entities in Home Assistant
Check the file *MQTT-Topics.txt* in this repository for more information.

**How ro read this file?**
Let's investigate the following example entry:
```
SENSORS_PER_CHARGEPOINT
       mqttTopicCurrentValue = {mqttRoot}/chargepoint/{deviceID}/{key}
               key="get/power",
```

For the device chargepoint, there is a sensor that subscribes to the MQTT topic
```
                {mqttRoot}/chargepoint/{deviceID}/get/power
# For example:  openWB    /chargepoint/0         /get/power
```

If you want to know to which sensor entity this MQTT topic is mapped, have a look into the file *const.py*.

Check the list ```SENSORS_PER_CHARGEPOINT``` and locate the entry with ```key="get/power"``````.

The property *name* corresponds to the entity name in Home Assistant.
In our example, the topic above is mapped to the sensor "Ladeleistung" of the device chargepoint.