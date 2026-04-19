{ pkgs }:
{
  projectRootFile = "flake.nix";
  programs.nixfmt.enable = true;
  programs.ruff.format = true;
  programs.ruff.check = true;
  programs.prettier.enable = true;
  programs.shellcheck.enable = true;
  programs.shfmt.enable = true;

  programs.mypy.enable = true;
  programs.mypy.directories = {
    "calendar-cli" = {
      extraPythonPackages =
        let
          types-icalendar = pkgs.callPackage ../calendar-cli/types-icalendar.nix {
            python = pkgs.python3;
          };
        in
        with pkgs.python3.pkgs;
        [
          icalendar
          pytest
          types-icalendar
          types-python-dateutil
        ];
    };
    "pexpect-cli" = {
      extraPythonPackages = with pkgs.python3.pkgs; [
        pexpect
        pytest
      ];
    };
    "gmaps-cli" = {
      extraPythonPackages = with pkgs.python3.pkgs; [
        pytest
      ];
    };
    "buildbot-pr-check" = {
      extraPythonPackages = with pkgs.python3.pkgs; [
        pytest
      ];
    };
    "browser-cli" = {
      extraPythonPackages = with pkgs.python3.pkgs; [
        websockets
      ];
    };
    "context7-cli" = { };
    "screenshot-cli" = {
      extraPythonPackages = with pkgs.python3.pkgs; [
        pytest
      ];
    };
    "tasker-cli" = {
      extraPythonPackages = with pkgs.python3.pkgs; [
        pytest
      ];
    };
    "kagi-search" = {
      extraPythonPackages = with pkgs.python3.pkgs; [
        beautifulsoup4
        types-beautifulsoup4
      ];
    };
    "n8n-cli" = {
      extraPythonPackages = with pkgs.python3.pkgs; [
        pytest
      ];
    };
    "weather-cli" = { };
  };

  settings.global.excludes = [
    "*.lock"
    "*.toml"
    "*.png"
    "*.svg"
  ];
}
