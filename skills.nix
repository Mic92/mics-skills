# Single source of truth for the skill ↔ package mapping.
#
# Each entry describes one home-manager-installable skill. Both
# `home-manager.nix` (the legacy `programs.mics-skills` option module) and
# `home-manager-new.nix` (per-skill `flake.homeModules.<name>`) consume this so
# adding a skill means touching exactly one place.
#
# The skill definition itself (SKILL.md and friends) ships inside the package
# at `$out/share/skills/<name>/`, so the home-manager modules symlink from
# the package output rather than the source tree.
#
# Fields (all optional):
#   package – package attr name from `self.packages.<system>` to install
#             (default: <name>). The package must carry
#             `share/skills/<name>/`.
#   extra   – additional home-manager module to merge in (only used by the
#             per-skill homeModules variant).
{
  browser-cli = { };
  browser-cli-with-extension = {
    package = "browser-cli";
    extra =
      { self }:
      { pkgs, ... }:
      {
        programs.firefox.profiles.default.extensions.packages = [
          self.packages.${pkgs.stdenv.hostPlatform.system}.browser-cli-extension
        ];
      };
  };
  buildbot-pr-check = { };
  calendar-cli = { };
  context7-cli = { };
  db-cli = { };
  gmaps-cli = { };
  kagi-search = { };
  n8n-cli = { };
  pexpect-cli = { };
  screenshot-cli = { };
  tasker-cli = { };
  weather-cli = { };
}
