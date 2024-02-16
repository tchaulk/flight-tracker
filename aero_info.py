# flighttracker/aero_info.py

"""
Responsible for retreiving, storing, and processing data from FlightAware API
"""

import json
from datetime import timedelta
import logging
import os
import requests

URL = "https://aeroapi.flightaware.com/aeroapi/flights/"
headers = {
    "Accept": "application/json; charset=UTF-8",
    "x-apikey": os.environ.get('FLIGHT_AWARE_API_KEY'),
}

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

def get_aero_data(fid: str, fake_check: bool = True) -> json:
    """Gets data from FlightAware API"""
    if fake_check:
        return ""
    response = requests.get(URL + fid, headers=headers, timeout=10)
    print("Checking Flight ID -", fid, "-")
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
                # ????
                print(
                    "There are no current flights listed that are in the air for id: ",
                    fid)
            return result
        print("No data found for ID [", fid, "]")
        return result
    # Print an error message if the request was not successful
    print(f"Error: {response.status_code}, {response.text}")
    return ""
