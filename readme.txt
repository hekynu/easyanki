1. The Project
Before moving files, ensure your folder looks like this:

app.py (The Python Logic)

flashcards.db (The SQLite Database)

requirements.txt (The 7-line library list)

templates/ (Folder containing index.html, study.html, etc.)

static/ (Folder for your images/CSS)

Your requirements.txt (Paste this inside):
Plaintext
Flask==3.1.3
Jinja2==3.1.6
MarkupSafe==3.0.2
Werkzeug==3.1.6
itsdangerous==2.2.0
blinker==1.9.0
click==8.2.1
2. Windows Setup (Desktop Mode)
Use this for testing or if you want your PC to be the server.

Install Python: Download from python.org. Check "Add to PATH".

Setup Environment:

Open PowerShell in your project folder.

Run: python -m venv venv

Run: .\venv\Scripts\activate

Run: pip install -r requirements.txt

Run it: python app.py

3. Raspberry Pi Setup
This is for a "Set it and Forget it" server in the corner of your room.

Step A: Preparation
Flash SD Card: Use Raspberry Pi Imager. Click the Cog/Settings icon.

Enable SSH: Set a username (pi) and password.

Enable Wi-Fi: Enter your home Wi-Fi details.

Install Tailscale: (Optional but recommended) Run curl -fsSL https://tailscale.com/install.sh | sh once logged in.

Step B: Moving the Files
From your Windows PowerShell, send your files to the Pi:

PowerShell
scp -r C:\Path\To\Your\Project\* pi@192.168.50.215:/home/pi/flashcards/
Step C: Setting up the "Brain" on the Pi
SSH into your Pi (ssh pi@192.168.50.215) and run:

Bash
cd ~/flashcards
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
4. "Start on Boot" Configuration (Systemd)
To ensure the cards are online even after a power outage, we turn the app into a system service.

Create Service File:
sudo nano /etc/systemd/system/flashcards.service

Paste this configuration:

Ini, TOML
[Unit]
Description=Japanese Flashcard Server
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/flashcards
ExecStart=/home/pi/flashcards/venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
Enable & Start:

Bash
sudo systemctl daemon-reload
sudo systemctl enable flashcards.service
sudo systemctl start flashcards.service
5. Connecting Your Phone
The app is now "Always On."

Get the IP: Your Pi's local IP (e.g., 192.168.50.215) or Tailscale IP (100.88.149.19).

The URL: Type http://[IP-ADDRESS]:8080 into your phone's browser.

See live logs (who's studying?): journalctl -u flashcards -f


Update code: Just SCP the new app.py over, then run sudo systemctl restart flashcards.
