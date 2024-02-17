# flighttracker/adsb_info.py

"""
Responsible for retreiving, storing, and processing data from ADSB API
"""

from datetime import datetime, timedelta
import json
import logging
import os
import requests


import aero_info

# 7am to 10pm
awakeTime = range(7, 22)
# examplehex_id = 'A1013F' # Current hex code for plane reg N621MM
URL_REG = "https://adsbexchange-com1.p.rapidapi.com/v2/registration/"
URL_HEX = "https://adsbexchange-com1.p.rapidapi.com/v2/icao/"

headers = {
    "X-RapidAPI-Key": os.environ.get('ADSB_API_KEY'),
    "X-RapidAPI-Host": "adsbexchange-com1.p.rapidapi.com",
}

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

class FlightData:
    """Handles ADBS Data"""

    # Identifier
    hex_id = ""
    registration = ""
    flight_num = ""

    # AeroInfo data
    flight_origin = ""
    flight_destination = ""
    landing_time = datetime.now()
    # Save the data so we don't have to get it more than once per-flight
    raw_aero_data = ""

    plane_in_air = False

    def __init__(self, fl_id: str, is_reg: bool = False):
        """Class Initializer"""
        if is_reg:
            self.registration = fl_id
        else:
            self.hex_id = fl_id

    def get_raw_adsb_data(self) -> json:
        """Pulls Adsb Data from API"""
        response = ""
        if self.registration:
            reg = self.registration
            print("Checking flight info for registration ID: ", reg)
            local_url_reg = URL_REG + reg + "/"
            print(local_url_reg)
            response = requests.get(
                local_url_reg, headers=headers, timeout=10
            )
        else:
            print("Checking flight info for hex ID: ", self.hex_id)
            local_url_hex = URL_HEX + self.hex_id + "/"
            print(local_url_hex)
            response = requests.get(
                local_url_hex, headers=headers, timeout=10
            )
        return response.json()

    def process_adsb(self, flight_data: json) -> bool:
        """Processes json received from Adsb"""
        processed_all = True
        hex_id = flight_data["hex"] if "hex" in flight_data else ""
        # Clean up flight ID by stringify and remove exterior spaces
        flight_id = (
            str(flight_data["flight"]).strip() if "flight" in flight_data else ""
        )
        reg = flight_data["r"] if "r" in flight_data else ""
        # Populate the member variables, print if the json data failed to get the info
        if hex_id == "":
            print("Couldn't find hex")
            processed_all = False
        # Typically if a flight is scrambled/hidden, this is the field that'll be omitted
        if reg == "":
            print("Couldn't find reg")
            processed_all = False
        if flight_id == "":
            print("Couldn't find flight_id")
            processed_all = False
        self.hex_id = hex_id
        self.registration = reg
        self.flight_num = flight_id
        return processed_all

    def in_the_air(self) -> bool:
        """
        Checks if a flight is in the air through ADSB, we
        just want to know if it's flying or not
        """
        # Only check during awake time
        if datetime.now().hour not in awakeTime:
            print("Go to bed")
            return False
        j_resp = self.get_raw_adsb_data()
        # Try hex_id first
        plane_id = self.registration if self.registration != "" else self.hex_id
        # The message field only pops up when there's an error
        if "message" in j_resp:
            print("There's an issue with ID " + plane_id + " ..." + j_resp["message"])
            return False
        if j_resp["msg"] == "No error" and j_resp["ac"]:
            altitude = j_resp["ac"][0]["alt_baro"]
            if (altitude == "ground") or (altitude < 20):
                print(
                    "Plane information is populating but the flight is at altitude:",
                     altitude
                )
                return False
            # If the flight is in the air then we should definit
            if self.registration == "":
                try:
                    self.registration = j_resp["ac"][0]['r']
                except(KeyError):
                    print("No registration included...")
            print("Flight ", plane_id, "is in the air")
            return True
        print(
            "Nothing reported from ", plane_id, ", last check at ",
            datetime.fromtimestamp(datetime.now().timestamp()),
        )
        return False

    def has_aero_data(self) -> bool:
        """Get aeroData from API if it exists"""
        self.raw_aero_data = aero_info.get_aero_data(
            self.registration, fake_check=False
        )
        # Probably better to just go off registration for getting AeroData
        if self.raw_aero_data == "":
            print("No JSON found")
            return False
        return True

    def process_aero_data(self) -> bool:
        """
        Pull useful data from AeroData, return false if we can't find the fields for
        some reason, but if the field exists, it should have valid data
        """
        try:
            curr_flight = self.raw_aero_data
            self.flight_origin = curr_flight["origin"]["name"]
            self.flight_destination = curr_flight["destination"]["name"]
            # Landing time will be defined as the estimated runway arrival time as this
            # should be closer to the correct time than scheduled
            date_format = "%Y-%m-%dT%H:%M:%SZ"
            self.landing_time = (
                datetime.strptime(curr_flight["estimated_on"], date_format)
                if "estimated_on" in curr_flight
                else datetime.now()
            )
            return True
        except (IndexError, ValueError):
            print("Couldn't process data for ID ", self.hex_id)
            print(self.raw_aero_data)
            return False

    def is_plane_on_ground(self) -> bool:
        """Checks if flight is registered to have landed or not"""
        j_resp = self.get_raw_adsb_data()
        plane_id = self.registration
        if "message" in j_resp:
            print("There's an issue with ID " + plane_id + " ... " + j_resp["message"])
            return False
        if j_resp["msg"] == "No error":
            if j_resp["ac"]:
                # alt_baro will read "Ground" if it's on the ground, will publish altitute otherwise
                altitude = j_resp["ac"][0]["alt_baro"]
                if (altitude == "ground") or (altitude < 20):
                    print("Plane ", self.registration, " has landed, altitude: ", altitude)
                    return True
            # At this point in the logic, we assume that we've gotten usable information in the past 
            # TODO, Find a better way to check this.
            elif j_resp["ac"] == None or j_resp["ac"] == "":
                # Flight has most likely landed and we just missed it landing
                print("Plane ", self.registration, " has stopped publishing information to ADSB")
                return True
        return False

    def set_hex(self, hex_id: str):
        """Set hex ID"""
        self.hex_id = hex_id

    def set_registration(self, reg: str):
        """Set registration"""
        self.registration = reg
