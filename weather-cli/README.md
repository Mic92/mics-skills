# weather-cli

A command-line tool for weather forecasts using the
[Bright Sky API](https://brightsky.dev/), which provides data from DWD
(Deutscher Wetterdienst). Covers ~5400 stations worldwide via MOSMIX forecasts,
with the densest observation network in Germany.

## Features

- Current weather conditions (closest observation to now)
- Multi-day forecasts (temperature range, condition, precipitation)
- Geocoding via OpenStreetMap Nominatim
- No API key required
- Pure Python stdlib, no external dependencies

## Installation

```bash
# Run directly
nix run github:Mic92/mics-skills#weather-cli -- Berlin

# Add to your flake
{
  inputs.mics-skills.url = "github:Mic92/mics-skills";
  # Then use: inputs.mics-skills.packages.${system}.weather-cli
}
```

## Usage

See [skills/weather-cli/SKILL.md](../skills/weather-cli/SKILL.md) for usage
examples.

## Data Source

[Bright Sky](https://brightsky.dev/) provides free access to DWD weather
station observations and MOSMIX forecast data. No API key is needed. MOSMIX
covers ~5400 stations worldwide; observation data is densest in Germany.

## License

MIT
