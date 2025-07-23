import asyncio
import json
import os
from datetime import datetime

import paho.mqtt.client as mqtt
from bleak import BleakScanner

# Configurations (set as env variables or hardcode for demo)
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC_BT", "/gw/laptop/status")

# Initialize MQTT client and connect with explicit client_id parameter to avoid argument conflicts
mqtt_client = mqtt.Client(client_id="BluetoothScannerPublisher", callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)

async def scan_and_publish():
    while True:
        devices = await BleakScanner.discover(timeout=0.5)  # Reduced discovery timeout
        messages = []
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"  # ISO-format UTC timestamp with milliseconds and Z suffix
        for device in devices:
            if device.address in ["C3:00:00:35:83:F6", "C3:00:00:35:83:EC"]:
                cleaned_mac = device.address.replace(":", "")
                messages.append({
                    "timestamp": timestamp,
                    "address": cleaned_mac,
                    "name": device.name,
                    "rssi": device.rssi,
                    "txpower": getattr(device, "tx_power", None)
                })
        if messages:
            payload = json.dumps(messages)
            mqtt_client.publish(MQTT_TOPIC, payload)
            print(f"Published: {payload}")
        await asyncio.sleep(0.1)  # Reduced sleep time for faster scanning

if __name__ == "__main__":
    try:
        asyncio.run(scan_and_publish())
    except KeyboardInterrupt:
        pass
    finally:
        mqtt_client.disconnect()
