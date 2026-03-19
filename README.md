# CamoFox Browser

Anti-detection browser integration for Agent Zero. Provides:

- 6 grouped agent tools covering all 48 CamoFox API endpoints
- Floating VNC viewer for CAPTCHA solving and visual debugging
- Session/cookie management and auth vault integration
- Configurable server URL, API key, and geo presets

## Requirements

- CamoFox server running (default: http://localhost:9377)
- Optional: `camofox` CLI for auth vault and scripting
- For visible browser mode: `xvfb`, `x11vnc`, `websockify`, and noVNC assets at `/opt/noVNC`
- The embedded viewer now runs through the normal Agent Zero URL, so users do not need to publish extra VNC ports in Docker
