import requests
from bs4 import BeautifulSoup
from telegram import Bot
import time
import logging
import traceback
import asyncio
import os
import codecs 
from datetime import datetime, timedelta

# Configure more detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ticket_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Telegram Bot Token and Chat ID
TELEGRAM_BOT_TOKEN = "TELEGRAM_BOT_TOKEN" 
TELEGRAM_CHAT_ID = "TELEGRAM_CHAT_ID"

# URL of the event page
EVENT_PAGE_URL = "https://fomobaku.com/en/page/events"

# Path to store the last known ticket status
LAST_STATUS_FILE = "last_status.txt"
LAST_NOTIFICATION_FILE = "last_notification.txt"

# Function to scrape website for ticket availability
def check_ticket_availability():
    try:
        logger.info(f"Attempting to fetch page: {EVENT_PAGE_URL}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Increase timeout and add more detailed error handling
        response = requests.get(EVENT_PAGE_URL, headers=headers, timeout=15)
        logger.debug(f"Response status code: {response.status_code}")
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Log the entire page text for debugging
        logger.debug(f"Full page content: {soup.text[:500]}...")  # First 500 chars

        # More aggressive search for ticket availability
        ticket_keywords = ['NEW YEAR', 'BUY TICKET', 'EVENT TICKET']
        
        # Check multiple possible indicators of ticket availability
        availability_indicators = any(
            keyword.lower() in soup.text.lower() 
            for keyword in ticket_keywords
        )

        if availability_indicators:
            logger.info("Potential ticket availability found")
            return "Tickets Potentially Available"
        else:
            logger.warning("No ticket availability indicators found")
            return "Tickets Not Available"

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during scraping: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return "Error"
    except Exception as e:
        logger.error(f"Unexpected error during scraping: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return "Error"

def read_last_status():
    try:
        if os.path.exists(LAST_STATUS_FILE):
            with open(LAST_STATUS_FILE, "r") as file:
                status = file.read().strip()
                logger.info(f"Read last status: {status}")
                return status
        else:
            logger.warning(f"Status file {LAST_STATUS_FILE} does not exist")
            return None
    except Exception as e:
        logger.error(f"Error reading status file: {e}")
        return None

def write_current_status(status):
    try:
        with open(LAST_STATUS_FILE, "w") as file:
            file.write(status)
        logger.info(f"Wrote current status: {status}")
    except IOError as e:
        logger.error(f"Error writing status file: {e}")

def read_last_notification_time():
    try:
        if os.path.exists(LAST_NOTIFICATION_FILE):
            with open(LAST_NOTIFICATION_FILE, "r") as file:
                return datetime.fromisoformat(file.read().strip())
        return None
    except Exception as e:
        logger.error(f"Error reading last notification file: {e}")
        return None

def write_last_notification_time():
    try:
        with open(LAST_NOTIFICATION_FILE, "w") as file:
            file.write(datetime.now().isoformat())
    except IOError as e:
        logger.error(f"Error writing last notification file: {e}")

async def send_telegram_notification(message, force=False):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        last_notification = read_last_notification_time()
        
        # Check if more than 30 minutes have passed since last notification or force flag is True
        if force or not last_notification or datetime.now() - last_notification > timedelta(minutes=30):
            if message == "Tickets Potentially Available":
                text = "Potential ticket availability detected for the New Year event! Check here: https://fomobaku.com/en/page/events"
            elif message == "Tickets Not Available":
                text = "Tickets are currently not available."
            else:
                text = f" Status: {message}"
            
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text.encode('utf-8').decode('latin-1'))
            write_last_notification_time()
            logger.info("Notification sent successfully!")
        else:
            logger.debug("Skipping notification due to recent send")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

async def main():
    logger.info("Starting ticket scraper...")
    consecutive_errors = 0
    max_consecutive_errors = 5
    last_status = read_last_status()

    while True:
        try:
            logger.debug("Checking ticket availability...")
            current_status = check_ticket_availability()
            logger.info(f"Current status: {current_status}")

            # Check if ticket availability status has changed
            if current_status != last_status:
                logger.info(f"Status changed from {last_status} to {current_status}")
                await send_telegram_notification(current_status)
                write_current_status(current_status)
                last_status = current_status
            else:
                # Force send a notification every 30 minutes to keep monitoring active
                await send_telegram_notification(current_status, force=True)
                logger.debug("Status unchanged, but sent periodic update")

            # Implement exponential backoff for errors
            if current_status == "Error":
                consecutive_errors += 1
                sleep_time = min(60 * (2 ** consecutive_errors), 3600)  # Max 1 hour
                logger.warning(f"Consecutive errors: {consecutive_errors}. Waiting {sleep_time} seconds")
            else:
                consecutive_errors = 0
                sleep_time = 300  # 5 minutes instead of 1 minute

            # Emergency exit if too many consecutive errors
            if consecutive_errors >= max_consecutive_errors:
                logger.critical("Too many consecutive errors. Exiting.")
                break

            await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("Script manually stopped.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            consecutive_errors += 1
            await asyncio.sleep(60)  # Wait 1 minute before retrying

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script manually stopped.")
