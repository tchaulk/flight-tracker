# flighttracker/flight_bot.py

"""
Pulls and sends flight information through Telegram when selected flights are in the air
"""

import asyncio
import logging
from datetime import datetime, timedelta
import os
from tzlocal import get_localzone
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from adsb_info import FlightData
import multi_key_dict

# ID of where you're sending the telegram message from
TEST_GROUP_ID = 0

# Flight data storage, can access data with both hex and registration
flight_dict = multi_key_dict.MultiKeyDict()
# List of flights actively being monitored: {id : [idType, isRecurring]}
active_flight_list = {"a1013f": ["hex", True]}

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# logging.disable(50)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the flight tracker, adds flights from active_flight_list"""
    global TEST_GROUP_ID
    TEST_GROUP_ID = update.effective_message.chat_id
    print("SEND ID = ", TEST_GROUP_ID)
    # Kicks off checker starting with adding all flights that are initially in active_flight_list
    for flight in active_flight_list:
        id_type = active_flight_list[flight][0]
        recurring = active_flight_list[flight][1]
        context.job_queue.run_once(
            callback=add_flight_job_callback,
            when=timedelta(seconds=1),
            name=str(TEST_GROUP_ID),
            data=[flight, id_type, recurring],
        )
    # Wait for flight list to populate the dictionary before moving forward
    while len(flight_dict) != len(active_flight_list):
        print("Waiting.... progress: [", len(flight_dict), " / ", len(active_flight_list), "]")
        await asyncio.sleep(1)
    monitoring_interval = timedelta(minutes=5)
    context.job_queue.run_repeating(
        callback=check_in_air,
        first=timedelta(seconds=1),
        interval=monitoring_interval,
        name=str(TEST_GROUP_ID),
    )


async def list_commands(update: Update, _) -> None:
    """Sends explanation on how to use the bot."""
    await update.message.reply_text(
        "Command List: \n /start - Starts the flight tracking \
                                    \n /help - Brings up this list \
                                    \n /add <id> <idType(reg, hex)> <recurring>- \
                                    Add a flight to the flight tracker, isRecurring \
                                    defaults to False \
                                    \n /remove - Remove a flight from the flight tracker \
                                    \n /list - List all flights being tracked"
    )


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


async def check_in_air(context: ContextTypes.DEFAULT_TYPE):
    """
    Check if a flight is in the air, if it is, we let the user know
    and kick of a flight_has_landed check to let the user know when
    the plane has reached it's destination
    """
    # Not user facing so this data should already be valid
    for hex_id in active_flight_list:
        # Find flight, it should already be in system
        print("Checking ", hex_id, " if it's airborn")
        current_flight = flight_dict[hex_id]
        print("Checking ", current_flight.hex_id, " if it's airborn")
        # If we're already in the air, we don't want to check this...although this might break if
        if current_flight.plane_in_air:
            return
        # Checks if the flight is in the air
        if current_flight.in_the_air():
            plane_emoji = "\U00002708"
            message = plane_emoji + " Flight " + current_flight.hex_id + " is in air"
            current_flight.plane_in_air = True
            # First time we check if plane has landed
            first_check = datetime.now()
            # Once we let the user know the flight is flying, we want to check for more metadata
            if current_flight.has_aero_data():
                # If we are able to process the AeroData then we can send it in the message
                if current_flight.process_aero_data():
                    if current_flight.flight_origin:
                        message += " \n Origin: " + current_flight.flight_origin
                    if current_flight.flight_destination:
                        message += (
                            " \n Destination: " + current_flight.flight_destination)
                    # We either start checking immediately or when the flight is supposed to land,
                    # depending if the data was provided
                    if current_flight.landing_time > datetime.now():
                        local_time = current_flight.landing_time
                        # Convert UTC time to local time zone, this conversion is only being done
                        # for readability of the telegram message
                        local_time = local_time.astimezone(get_localzone())
                        message += "\n Estimated Landing time: " + str(local_time)
                        # Stop the job that checks if the flight is in the air, we only needed
                        # to do it as long as there was a flight we were waiting on.
                else:
                    print("Failed to process all Aero Data for ", current_flight.hex_id)
            else:
                print("Failed to get Aero Data for ", current_flight.hex_id)

            print("Starting landing check for ", current_flight.hex_id)
            context.job_queue.run_repeating(
                plane_has_landed,
                interval=timedelta(seconds=300),
                first=first_check + timedelta(seconds=2),
                name=str(TEST_GROUP_ID)
                + "_Landing_"
                + str(current_flight.hex_id),
                data=current_flight.hex_id,
            )
            await context.bot.send_message(TEST_GROUP_ID, message)


async def plane_has_landed(context: ContextTypes.DEFAULT_TYPE):
    """Lets the user know when the plane has landed"""
    print("Checking if flight has landed...")
    flight_data = flight_dict[context.job.data]
    if not flight_data.plane_in_air:
        return
    if flight_data.is_plane_on_ground():
        flight_data.plane_in_air = False
        text = "Plane " + flight_data.hex_id + "has landed!"
        if not active_flight_list[flight_data.hex_id][1]:
            print("Removing", context.job.name)
            remove_job_if_exists(context.job.name, context)
            context.job_queue.run_once(
                remove_flight_job_callback,
                when=timedelta(seconds=1),
                name=str(TEST_GROUP_ID),
                data=[flight_data.hex_id],
                )
        await context.bot.send_message(TEST_GROUP_ID, text)
        # To keep things clean, we want to remove the landing check
        remove_job_if_exists(str(TEST_GROUP_ID)
            + "_Landing_" + str(flight_data.hex_id), context)

async def add_flight_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a flight to list of flights to be checked."""
    fl_id = ""
    try:
        fl_id = context.job.data[0]
        # (fixme) Add flight number as an argument, ideally this could be in the form of
        # a second prompt asking what we just provided
        is_reg = context.job.data[1] == "reg"
        # Make sure to convert to lower if this is a hex id
        fl_id = fl_id if is_reg else fl_id.lower()
        repeat = context.job.data[2] if len(context.job.data) > 2 else False
    except (IndexError, ValueError):
        await context.bot.send_message(
            TEST_GROUP_ID, "Usage: /add <id> <idType(reg, hex)> <recurring>"
        )
        return
    # Look for flight, we're starting from scratch whenever we call notify flight,
    # so replace the current flight_data, mainly because this ensures we're working
    # off of current data
    new_flight = FlightData(fl_id, is_reg)
    raw_json = new_flight.get_raw_adsb_data()
    if "message" in raw_json:
        print("There's an issue with ID " + fl_id + " ..." + raw_json["message"])
    if raw_json["msg"] == "No error" and raw_json["ac"]:
        if new_flight.process_adsb(raw_json["ac"][0]):
            print("Processed all fields successfully")
        else:
            print("Failed to populate all fields")
    else:
        print("WARNING: Either ", fl_id, "is an invalid ID, or the flight is not airborn yet \
              so we can't get data")
    # Add flight to multi-key dict, technically if a flight is not in the air we don't
    # add the registration or anything.
    # TODO, should I be updating the dict if a registration doesn't
    # exist when in in_the_air ?
    if fl_id in flight_dict.key_map.keys():
        print("Adding updated flight_data to id: ", fl_id)
        flight_dict[fl_id] = new_flight
    else:
        i_text = ""
        key_list = []
        if new_flight.hex_id:
            # We should always have the hex_id to rely on, registration is never guaraunteed
            i_text += "Assigning hex_id " + new_flight.hex_id
            key_list.append(new_flight.hex_id)
            print(f"Added {new_flight.hex_id} to flight_dict")
        if new_flight.registration:
            i_text += " \n Assigning registration " + new_flight.registration
            # Add a new mapping if there is no registration, otherwise just add to the key
            key_list.append(new_flight.registration)

        flight_dict.add_mapping(new_flight, *key_list)
        print(i_text)
        try:
            active_flight_list[fl_id] = [is_reg, repeat]
        except(KeyError, IndexError, ValueError):
            print("Failed to add to active flight list???")
    text = "Flight checker has added ID: " + fl_id + " to the list!"
    await context.bot.send_message(TEST_GROUP_ID, text)


async def add_flight_job_callback(context: ContextTypes.DEFAULT_TYPE):
    """Handles when attempting to call add_flight as a job"""
    # Extracting data passed to the job
    flight, hex_value, recurring = context.job.data

    # Call the shared callback function
    context.job_queue.run_once(
        add_flight_callback,
        when=timedelta(seconds=1),
        name=str(TEST_GROUP_ID),
        data=[flight, hex_value, recurring],
    )


# Command handler for /add command
async def add_flight_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles when attempting to call add_flight as a telegram command"""
    
    global TEST_GROUP_ID
    TEST_GROUP_ID = update.message.chat_id
    # Extracting parameters from the command
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Invalid command format. \n Usage: /add <id> <idType(reg, hex)> <recurring>"
        )
        return

    flight = args[0]
    hex_value = args[1]
    recurring = args[2] if len(args) > 2 else False
    # Call the shared callback function
    context.job_queue.run_once(
        add_flight_callback,
        when=timedelta(seconds=1),
        name=str(TEST_GROUP_ID),
        data=[flight, hex_value, recurring],
    )


async def remove_flight_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles when attempting to call remove_flight as a telegram command"""

    global TEST_GROUP_ID
    TEST_GROUP_ID = update.message.chat_id
    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "Invalid command format. \n Usage: /remove <id>"
        )
        return

    # Call the shared callback function
    context.job_queue.run_once(
        remove_flight_callback,
        when=timedelta(seconds=1),
        name=str(TEST_GROUP_ID),
        data=args[0],
    )


async def remove_flight_job_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles when attempting to call remove_flight as a job"""

    # Call the shared callback function
    context.job_queue.run_once(
        remove_flight_callback,
        when=timedelta(seconds=1),
        name=str(TEST_GROUP_ID),
        data=context.job.data[0],
    )


async def remove_flight_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a flight from the flight list."""
    text = ""
    r_id = context.job.data
    if r_id is None:
        text = "Usage: /remove <id>"
    elif r_id in active_flight_list.keys():
        text = "Removing ID: [" + r_id + "] from list"
        try:
            del active_flight_list[r_id]
        except KeyError:
            text = "Failed to remove ID?"
    else:
        text = "ID: [" + r_id + "] not found in list"
    await context.bot.send_message(TEST_GROUP_ID, text)


async def list_ids(update: Update, _) -> None:
    """Provide a list of IDs currently being tracked by the program"""
    text = "Current list of ids being tracked:"
    for key in active_flight_list:
        text += "\n" + key
    await update.message.reply_text(text)
    return


def main() -> None:
    """Run bot."""
    # Create the Application and pass it your bot's token.
    application = (
        Application.builder()
        .token(str(os.environ.get("TELEGRAM_FLIGHT_BOT_KEY")))
        .build()
    )

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", list_commands))
    application.add_handler(CommandHandler("add", add_flight_command))
    application.add_handler(CommandHandler("remove", remove_flight_command))
    application.add_handler(CommandHandler("list", list_ids))
    print("Ready to start!")

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
