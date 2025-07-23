import asyncio
import json
import logging
import os
import threading
import time
from collections import deque, defaultdict

import numpy as np
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from calc import TrilaterationController
from controller import Controller
from environment import *
from filter import apply_kalman_filter, initialize_kalman_filter
from graph import animate, set_on_close
from utils import convert_string_to_datetime

RUN_PIXEL_DISPLAY = False  # Whether to run the pixel display
GRAPH_REFRESH_INTERVAL = 2  # Refresh interval for the graph (seconds)
DISPLAY_REFRESH_INTERVAL = 4  # Refresh interval for the pixe ldisplay (seconds)

# Load env variables from .env file
load_dotenv()

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# State to stop the threads
stop_threads = False

# Environment variables
host = os.getenv("MQTT_HOST")
port = int(os.getenv("MQTT_PORT"))
mqtt_topic_1 = os.getenv("MQTT_TOPIC_1")
mqtt_topic_2 = os.getenv("MQTT_TOPIC_2")
mqtt_topic_3 = os.getenv("MQTT_TOPIC_3")
if mqtt_topic_1: mqtt_topic_1 = mqtt_topic_1.strip()
if mqtt_topic_2: mqtt_topic_2 = mqtt_topic_2.strip()
if mqtt_topic_3: mqtt_topic_3 = mqtt_topic_3.strip()

# Load tag configuration
no_of_tags = int(os.getenv("NO_OF_TAGS", "1"))
tag_macs = []
for i in range(1, no_of_tags + 1):
    tag_mac = os.getenv(f"TAG{i}_MAC")
    if tag_mac:
        tag_macs.append(tag_mac.strip().upper())  # Store MAC addresses in uppercase for comparison

logging.info(f"Tracking {no_of_tags} tags: {tag_macs}")

if not all([host, port, mqtt_topic_1, mqtt_topic_2, mqtt_topic_3]) or not tag_macs:
    logging.error("Required environment variables not set")
    exit(1)

# Create a client instance
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "SubscriberClient")

# Set authentication for the client
# client.username_pw_set(username, password)

# Data structure to store readings for each tag from each receiver
tags_data = {}
for tag_mac in tag_macs:
    tags_data[tag_mac] = {
        "receiver_1": deque(maxlen=20),
        "receiver_2": deque(maxlen=20),
        "receiver_3": deque(maxlen=20),
        "position": (0, 0),  # Default position
        "kalman_filters": {
            "receiver_1": initialize_kalman_filter(),
            "receiver_2": initialize_kalman_filter(),
            "receiver_3": initialize_kalman_filter(),
        }
    }
    
    # Initialize with test data
    for receiver in ["receiver_1", "receiver_2", "receiver_3"]:
        tags_data[tag_mac][receiver].append({
            "time": "2021-08-01 12:00:00", 
            "address": "address_1", 
            "rssi": -42, 
            "filtered_rssi": [-42],
            "mac": tag_mac
        })

# Initialize the trilateration controller
locationEstimator = TrilaterationController(
    bp_1=RECEIVER_1_POS,
    bp_2=RECEIVER_2_POS,
    bp_3=RECEIVER_3_POS,
    measured_power_1=RECEIVER_1_TX_POWER,
    measured_power_2=RECEIVER_2_TX_POWER,
    measured_power_3=RECEIVER_3_TX_POWER,
    path_loss_exponent=PATH_LOSS_EXPONENT,
)


# MQTT event handlers
def on_connect(client, userdata, flags, return_code):
    if return_code != 0:
        return logging.info("could not connect, return code:", return_code)

    logging.info("Connected to broker")
    logging.info("Subscribing to topics:")
    logging.info(" - " + mqtt_topic_1)
    logging.info(" - " + mqtt_topic_2)
    logging.info(" - " + mqtt_topic_3)
    client.subscribe(mqtt_topic_1)
    client.subscribe(mqtt_topic_2)
    client.subscribe(mqtt_topic_3)


def on_message(client, userdata, message):
    try:
        decoded_message = message.payload.decode("utf-8")
        logging.info(f"Raw message received on {message.topic}: {decoded_message}")
        response_list = json.loads(decoded_message)  # Parse JSON payload as a list

        # Select the element containing an RSSI value
        response = next((item for item in response_list if "rssi" in item), None)
        if not response:
            raise ValueError("No valid element with 'rssi' found in message")
            
        # Make sure required fields exist
        if "address" not in response:
            response["address"] = "unknown"
        
        # Check for MAC address
        tag_mac = response.get("mac", "").upper()
        if tag_mac not in tag_macs:
            logging.info(f"Ignoring message from unregistered MAC: {tag_mac}")
            return
            
        # Handle timestamp - ensure we have a time field
        if "time" not in response:
            if "timestamp" in response:
                # Use timestamp field if available but convert to time
                response["time"] = convert_string_to_datetime(response["timestamp"])
            else:
                # Use current time if no timestamp is available
                response["time"] = convert_string_to_datetime(time.strftime("%Y-%m-%d %H:%M:%S"))

        # Determine which receiver this is from and apply Kalman filter
        receiver_key = None
        if message.topic == mqtt_topic_1:
            receiver_key = "receiver_1"
        elif message.topic == mqtt_topic_2:
            receiver_key = "receiver_2"
        elif message.topic == mqtt_topic_3:
            receiver_key = "receiver_3"
        else:
            logging.error("Unknown topic received: " + message.topic)
            return
            
        # Apply filter and store data
        kf = tags_data[tag_mac]["kalman_filters"][receiver_key]
        response["filtered_rssi"] = apply_kalman_filter(kf, response["rssi"])
        tags_data[tag_mac][receiver_key].append(response)
        
        logging.info(f"Tag {tag_mac} - {receiver_key} updated with RSSI: {response['rssi']}, filtered: {response['filtered_rssi']}")

    except Exception as e:
        logging.error(f"Error processing message on topic {message.topic}: {str(e)}")
        logging.error(f"Message payload: {message.payload}")
        import traceback
        logging.error(traceback.format_exc())


# Assign event handlers
client.on_connect = on_connect
client.on_message = on_message

# Bluetooth controller
if RUN_PIXEL_DISPLAY:
    bt = Controller("DC:03:BB:B0:67:4A")

    # Set the beacons on the display
    bt.set_beacons(
        [
            locationEstimator.scale_coordinates(*RECEIVER_1_POS),
            locationEstimator.scale_coordinates(*RECEIVER_2_POS),
            locationEstimator.scale_coordinates(*RECEIVER_3_POS),
        ]
    )

    # Create a global event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.set_event_loop(loop)

    async def update_plot(tag_positions):
        """
        Update the plot with positions for all tags.

        Parameters:
        tag_positions (dict): Dictionary mapping tag MACs to (x,y) positions

        Returns:
        None
        """
        logging.info(f"+++ Updating plot with positions: {tag_positions}")
        # Note: The current display may need to be enhanced to show multiple tags
        # Here we're just showing the first tag for compatibility
        if tag_positions:
            first_tag = list(tag_positions.keys())[0]
            x, y = tag_positions[first_tag]
            await bt.plot(x, y)


def process_values():
    while not stop_threads:
        tag_positions = {}
        
        for tag_mac in tag_macs:
            tag_data = tags_data[tag_mac]
            
            # Check if we have data for all receivers
            if (tag_data["receiver_1"] and tag_data["receiver_2"] and 
                tag_data["receiver_3"]):
                
                logging.info(f"Tag {tag_mac} - Latest Values: {' | '.join(str(tag_data[rec][-1]['rssi']) for rec in ['receiver_1', 'receiver_2', 'receiver_3'])}")
                logging.info(f"Tag {tag_mac} - Latest Filtered: {' | '.join(str(tag_data[rec][-1]['filtered_rssi']) for rec in ['receiver_1', 'receiver_2', 'receiver_3'])}")

                # Calculate the estimated position
                rssi_1 = tag_data["receiver_1"][-1]["filtered_rssi"][0]
                rssi_2 = tag_data["receiver_2"][-1]["filtered_rssi"][0]
                rssi_3 = tag_data["receiver_3"][-1]["filtered_rssi"][0]

                # Update the position
                position = locationEstimator.get_position(rssi_1, rssi_2, rssi_3)
                tag_data["position"] = position
                tag_positions[tag_mac] = position
                
                logging.info(f"Tag {tag_mac} - Estimated position: {position}")
            else:
                logging.info(f"Tag {tag_mac} - Not enough data to calculate position")

        # Update the display with all tag positions
        if RUN_PIXEL_DISPLAY and tag_positions:
            loop.run_until_complete(update_plot(tag_positions))

        time.sleep(DISPLAY_REFRESH_INTERVAL)


def run_graph():
    def get_updated_data():
        # This function gathers position data for all tags
        tags_positions = {}
        tags_base_stations = {}
        
        for tag_mac in tag_macs:
            tag_data = tags_data[tag_mac]
            
            if (tag_data["receiver_1"] and tag_data["receiver_2"] and 
                tag_data["receiver_3"]):
                # Calculate base stations and distances for this tag
                base_stations = [
                    {
                        "coords": RECEIVER_1_POS,
                        "distance": locationEstimator.get_distance(
                            tag_data["receiver_1"][-1]["filtered_rssi"][0], 1
                        ),
                    },
                    {
                        "coords": RECEIVER_2_POS,
                        "distance": locationEstimator.get_distance(
                            tag_data["receiver_2"][-1]["filtered_rssi"][0], 2
                        ),
                    },
                    {
                        "coords": RECEIVER_3_POS,
                        "distance": locationEstimator.get_distance(
                            tag_data["receiver_3"][-1]["filtered_rssi"][0], 3
                        ),
                    },
                ]
                
                position = locationEstimator.trilaterate(
                    base_stations[0]["distance"],
                    base_stations[1]["distance"],
                    base_stations[2]["distance"],
                )
                
                tags_base_stations[tag_mac] = base_stations
                tags_positions[tag_mac] = position
        
        # The function returns data for display including all tags' positions
        if tags_positions:
            first_tag = list(tags_positions.keys())[0]
            return (
                tags_base_stations[first_tag],
                tags_positions[first_tag],
                list(tags_data[first_tag]["receiver_1"]),
                list(tags_data[first_tag]["receiver_2"]),
                list(tags_data[first_tag]["receiver_3"]),
                tags_positions,  # This contains all tags' positions for rendering
            )
        else:
            # Return empty data if no tag data is available
            empty_stations = [{
                "coords": pos,
                "distance": 0
            } for pos in [RECEIVER_1_POS, RECEIVER_2_POS, RECEIVER_3_POS]]
            return (empty_stations, (0, 0), [], [], [], {})

    # The graph animation is already being called
    animate(
        get_updated_data()[0],
        (0, 0),
        get_updated_data,
        interval=GRAPH_REFRESH_INTERVAL * 1000,
    )


def run():
    global stop_threads

    try:
        logging.info("Connecting to broker")
        client.connect(host, port)

        # Start the processing thread
        logging.info("Starting processing thread")
        processing_thread = threading.Thread(target=process_values, daemon=True)
        processing_thread.start()

        # Start the MQTT subscriber loop in a new thread
        logging.info("Starting MQTT subscriber")
        mqtt_thread = threading.Thread(target=client.loop_forever, daemon=True)
        mqtt_thread.start()

        # Set on graph close (raise KeyboardInterrupt)
        def on_close(event):
            logging.info("Closing graph")

        set_on_close(on_close)

        # Start the graph animation in the main thread
        logging.info("Starting graph animation")
        run_graph()

    except KeyboardInterrupt:
        logging.info("Gracefully shutting down...")

        # Stop the threads
        stop_threads = True
        client.disconnect()
        logging.info("MQTT disconnected.")

        processing_thread.join()
        logging.info("Processing (display) thread stopped.")

        mqtt_thread.join()
        logging.info("MQTT thread stopped.")

        # Stop bt
        if RUN_PIXEL_DISPLAY:
            loop.run_until_complete(bt.disconnect())
            logging.info("Bluetooth disconnected.")

        # Exit the program
        exit(0)


if __name__ == "__main__":
    run()
