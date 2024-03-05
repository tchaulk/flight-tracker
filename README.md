# flight-tracker
Track flights that are publicly available to view through ADSB API, polling every 5 minutes. 
Additional plane data will be included for publicly available flights, private flights can still be tracked.

## Prerequisites
- python-telegram-bot: https://docs.python-telegram-bot.org/
    - Create a telegram bot: https://core.telegram.org/bots#how-do-i-create-a-bot
- adsbexchange: https://rapidapi.com/adsbx/api/adsbexchange-com1
- aeroapi.flightaware: https://www.flightaware.com/aeroapi/portal/#overview


## Start
1. Clone the repository:

`git clone https://github.com/tchaulk/flight-tracker`

`cd flight-tracker`

`./flight_bot.py`

## Usage

Once the script is started, send the following commands to the telegram bot:

- `/start` - Starts the flight tracking
- `/help` - Brings up this list
- `/add $id $idType(reg, hex) $recurring` - Add a flight to the flight tracker, recurring defaults to False
- `/remove` - Remove a flight from the flight tracker
- `/list` - List all flights being tracked


