# Browser CLI Bugs

No known bugs.

## Known gotchas

- **Policy installs are version-gated.** `force_installed` compares
  `manifest.version` against the profile's installed copy and skips if
  equal. Editing extension code without bumping the version means the
  profile xpi never updates, even after a fresh nix build + browser
  restart. Bump `manifest.json` `version` on every shipped change.
