# Zigbee Exporter

Home Assistant custom component that automatically exports your Zigbee2MQTT device list to a CSV file and a searchable HTML dashboard.

## Installation

1. Copy the `custom_components/z2m_inventory` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings > Devices & Services > Add Integration** and search for **Zigbee Exporter**.
4. Configure your Zigbee2MQTT topic (default is `zigbee2mqtt/bridge/devices`).

## Usage

Once installed, the integration automatically subscribes to your MQTT broker. Every time Zigbee2MQTT updates its device list (or on Home Assistant startup), it generates two files in your `www` folder:

- `/config/www/z2m_inventory/z2m_devices.csv`
- `/config/www/z2m_inventory/z2m_devices.html`

You can access the interactive HTML dashboard directly from your browser:
`http://<YOUR_HA_IP>:8123/local/z2m_inventory/z2m_devices.html`

You can also trigger a manual refresh using the `z2m_inventory.generate` service.
