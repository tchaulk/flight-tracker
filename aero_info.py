# flighttracker/aero_info.py

"""
Responsible for retreiving, storing, and processing data from FlightAware API
"""

import json
from datetime import timedelta
import logging as log
import os
import requests

URL = "https://aeroapi.flightaware.com/aeroapi/flights/"
headers = {
    "Accept": "application/json; charset=UTF-8",
    "x-apikey": os.environ.get('FLIGHT_AWARE_API_KEY'),
}

aeLog = log.getLogger("aero_info")

# Enable logging 
aeLog.setLevel(log.INFO)
formatter = log.Formatter('%(asctime)s - %(name)s - %(funcName)s:%(lineno)d - [%(levelname)s] - %(message)s')
handler = log.StreamHandler()
handler.setFormatter(formatter)
aeLog.propagate = False

# Add the console handler to the logger
aeLog.addHandler(handler)

def get_aero_data(fid: str, fake_check: bool = True) -> json:
    """Gets data from FlightAware API"""
    if fake_check:
        return ""
    response = requests.get(URL + fid, headers=headers, timeout=10)
    aeLog.info(f"Checking Flight ID -{fid}-")
    # # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Parse and work with the JSON response
        json_data = response.json()
        result = ""
        if "flights" in json_data:
            # If we got here then the correct flight information exists...it's just hiding
            # among a bunch of other data
            for data in json_data["flights"]:
                if "En Route" in data["status"]:
                    result = data
            if result == "":
                # ???? This should not happen, there should always be data in "flights"
                aeLog.error(
                    f"There are no current flights listed that are in the air for id: \
                    {fid}")
            return result
        aeLog.warn(f"No data found for ID [ {fid} ]")
        return result
    # Print an error message if the request was not successful
    aeLog.error(f"Error: {response.status_code}, {response.text}")
    return ""
