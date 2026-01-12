# gmaps-cli

A simple command-line tool to search for places and get directions using Google
Maps API.

## Features

- Search for specific places
- Find multiple places nearby
- Get directions between locations
- Simple text output
- Secure API key management via command

## Setup

1. Get a Google Maps API key:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable "Places API" and "Directions API"
   - Create credentials → API key
   - Optionally restrict the key to Places API and Directions API

2. Store your API key securely (e.g., using `pass`, `rbw`, or environment
   variable)

3. Setup gmaps-cli with a command to retrieve your API key:

   ```bash
   # Using pass
   gmaps-cli setup --api-key-command "pass show google-maps-api-key"

   # Using rbw (Bitwarden)
   gmaps-cli setup --api-key-command "rbw get google-maps-api-key"

   # Using environment variable
   gmaps-cli setup --api-key-command "echo $GOOGLE_MAPS_API_KEY"
   ```

## Usage

See [skills/gmaps-cli/SKILL.md](../skills/gmaps-cli/SKILL.md) for usage examples.

## Configuration

The configuration is stored in `~/.config/gmaps-cli/config.json`. It contains
the command used to retrieve your API key, ensuring the key itself is never
stored in plaintext.

## License

MIT
