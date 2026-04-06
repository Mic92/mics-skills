# db-cli

CLI for Deutsche Bahn train connections. Wraps
[db-vendo-client](https://github.com/public-transport/db-vendo-client), which
talks to the same backend as the bahn.de app — so unlike most transit tooling,
**there is no API key, registration, or rate limit setup**. It just works.

## Features

- Fuzzy station name matching — `Köln` resolves to `KÖLN (8096022)` before the
  journey query runs, so you don't need to know IBNR station IDs
- Relative time parsing — `"in 30 minutes"`, `"by 18:00"` (rolls to tomorrow if
  already past), or full ISO 8601
- Deutschlandticket filter (`-t`) — drops ICE/IC/EC and shows only what the €58
  ticket actually covers
- Booking link — every search ends with a pre-filled `bahn.de/buchung` URL with
  your stations, time, and ticket filter encoded, so you can click through to
  pay without re-entering anything

## Install

```bash
nix run github:Mic92/mics-skills#db-cli -- "Berlin Hbf" "München Hbf"
```

Or add `mics-skills.packages.${system}.db-cli` to your home-manager packages.

## Usage

See [skills/db-cli/SKILL.md](../skills/db-cli/SKILL.md) for command examples.

## Development

```bash
npm install
npm run lint
```

The journey display logic lives in `lib/journey-display.mjs`; the bahn.de URL
encoding (which is undocumented and was reverse-engineered from browser
traffic) is in `lib/bahn-url-builder.mjs`.

## License

ISC
