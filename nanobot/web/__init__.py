"""Optional static asset namespace.

The React/Vite WebUI frontend is not bundled in this Telegram-focused build.
The package remains so older imports can resolve, and deployments may still
mount a custom ``dist/`` directory for the WebSocket channel if needed.
"""
