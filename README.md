# Zigbee Exporter

Home Assistant custom component that automatically exports your Zigbee2MQTT device list to a CSV file. Includes a standalone HTML dashboard to aggregate CSVs from multiple Home Assistant instances.

## Installation

1. Copy the `custom_components/z2m_inventory` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings > Devices & Services > Add Integration** and search for **Zigbee Exporter**.
4. Configure your Zigbee2MQTT topic (default is `zigbee2mqtt/bridge/devices`).

## Usage

Once installed, the integration automatically subscribes to your MQTT broker. Every time Zigbee2MQTT updates its device list (or on Home Assistant startup), it generates a CSV file in your `www` folder:

- `/config/www/z2m_inventory/z2m_devices.csv`

You can also trigger a manual refresh using the `z2m_inventory.generate` service.

## Multi-Instance Dashboard

This repository includes a standalone `dashboard.html` file designed specifically for users running multiple Home Assistant instances.

1. Open `dashboard.html` in your browser.
2. Download the `z2m_devices.csv` file from each of your Home Assistant instances.
3. Drag and drop all the CSV files onto the dashboard page.
4. The dashboard will automatically aggregate all devices into a single, unified, searchable table, allowing you to filter by specific instances.
