MOTOR TOWN TELEMETRY DASHBOARD
==============================

A desktop telemetry dashboard for Motor Town using the game's Native-v1 UDP
telemetry protocol.


RELEASES
=============================

The newest Releases are found here: https://github.com/LucBre-2009/motor-town-telemetry-dashboard/releases




FILES
-----
motor_town_dashboard.pyw
    Main dashboard application.

README.txt
    This documentation.

PYTHON VERSION
--------------
Recommended: Python 3.10 or newer.

On Windows, use a normal 64-bit Python installation with tkinter included.
Python's official Windows installer normally includes tkinter (Tkinter).

DEPENDENCIES
------------
This project intentionally uses Python's STANDARD LIBRARY ONLY.

No pip packages are required and the script does not install external
Python packages.

Modules used by the dashboard include:
- tkinter / tkinter.messagebox  - graphical user interface
- socket                       - UDP telemetry input
- struct                       - decoding Native-v1 packets
- threading                    - background telemetry receiver
- json                         - local configuration
- time / math                  - timing, smoothing and calculations
- sys / ctypes                 - Windows fullscreen/window handling
- subprocess / importlib       - dependency/setup support

There is no Docker requirement and no external account or online service is
required for the dashboard itself.

MOTOR TOWN TELEMETRY SETTINGS
-----------------------------
The game settings are located here:

1. Start Motor Town.
2. Press ESCAPE to open the game menu.
3. Open OPTIONS.
4. Open GAMEPLAY.
5. Find "Telemetry Data Output".
6. Turn Telemetry Data Output ON.
7. Configure the destination:

   IP:   127.0.0.1
   Port: 33330

8. Select/enable Native-v1 if the game presents a telemetry protocol option.
9. Start driving or otherwise move the vehicle so telemetry packets are sent.

The dashboard listens locally on UDP 127.0.0.1:33330.

FIRST START
-----------
On the first launch, a window displays the setup information and
explains the GUI.

The dashboard itself installs no external dependencies. After the setup
message, press Enter to start the graphical dashboard.

If the setup has already been completed, the dashboard can start directly.

CONFIGURATION / SETTINGS
------------------------
The dashboard has its own Settings page for dashboard preferences such as:
- Accent/theme color
- Speed unit (km/h or mph)
- Telemetry host/port where supported by the UI

These dashboard settings are stored locally in the configuration file used
by the application.

Important: Motor Town's telemetry settings are configured IN THE GAME under:

Options > Gameplay > Telemetry Data Output

They are separate from the dashboard's visual/settings options.

NATIVE-V1 TELEMETRY
-------------------
The dashboard expects Motor Town Native-v1 UDP packets.

Default endpoint:
127.0.0.1:33330

Native-v1 packets used by this dashboard are 153 bytes long.

The dashboard reads values such as:
- Vehicle speed
- Engine RPM / maximum RPM
- Current gear
- Throttle
- Brake
- Clutch
- Steering
- Handbrake
- Fuel
- Local acceleration / G-force
- Vehicle flags such as reverse, lights, ABS, TCS and cruise control
- Position / movement information

RUNNING THE DASHBOARD
---------------------
Just double click on the python file in your explorer when you want to use it.

FULLSCREEN
----------
Press F11 to enter the dashboard's fullscreen mode.

The fullscreen mode is intended to cover the complete monitor area without
the Windows taskbar.

TROUBLESHOOTING
---------------
No telemetry / dashboard stays disconnected:

1. Check that Motor Town is running.
2. Press ESC in Motor Town.
3. Go to Options > Gameplay.
4. Check that Telemetry Data Output is ON.
5. Check IP = 127.0.0.1.
6. Check Port = 33330.
7. Check that Native-v1 is selected/enabled if the game offers the choice.
8. Move the vehicle so telemetry packets are actually generated.

If Python reports that tkinter is missing, install Python again with the
standard tkinter/Tk component enabled.

PRIVACY / NETWORK
-----------------
The dashboard is designed for local telemetry input.
Its default telemetry endpoint is the local machine:
127.0.0.1:33330

It does not require an account, cloud service, or external telemetry server.

LICENSE / PROJECT NOTES
-----------------------
This README documents the current local dashboard build. Motor Town and its
telemetry protocol are separate software/products and remain the property of
their respective owners.
