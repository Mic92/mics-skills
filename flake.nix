{
  description = "LLM-useful CLI tools and skills";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    treefmt-nix.url = "github:numtide/treefmt-nix";
    treefmt-nix.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      imports = [
        inputs.treefmt-nix.flakeModule
      ];

      flake.homeManagerModules.default = import ./home-manager.nix;

      perSystem =
        {
          pkgs,
          self',
          lib,
          ...
        }:
        {
          checks =
            let
              packages = lib.mapAttrs' (n: lib.nameValuePair "package-${n}") self'.packages;
            in
            packages;

          packages = {
            browser-cli = pkgs.python3.pkgs.callPackage ./browser-cli { };
            buildbot-pr-check = pkgs.python3.pkgs.callPackage ./buildbot-pr-check { };
            browser-cli-extension = (pkgs.callPackages ./firefox-extensions { }).browser-cli-extension;
            calendar-cli = pkgs.callPackage ./calendar-cli {
              inherit (pkgs) python3 vdirsyncer msmtp;
            };
            context7-cli = pkgs.python3.pkgs.callPackage ./context7-cli { };
            db-cli = pkgs.callPackage ./db-cli { };
            gmaps-cli = pkgs.python3.pkgs.callPackage ./gmaps-cli { };
            kagi-search = pkgs.python3.pkgs.callPackage ./kagi-search { };
            n8n-cli = pkgs.python3.pkgs.callPackage ./n8n-cli { };
            pexpect-cli = pkgs.callPackage ./pexpect-cli { };
            screenshot-cli = pkgs.python3.pkgs.callPackage ./screenshot-cli {
              spectacle = if pkgs.stdenv.hostPlatform.isLinux then pkgs.kdePackages.spectacle else null;
            };
            tasker-cli = pkgs.python3.pkgs.callPackage ./tasker-cli {
              inherit (pkgs) android-tools makeWrapper;
            };
            weather-cli = pkgs.python3.pkgs.callPackage ./weather-cli { };
          };

          treefmt = {
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
                    types-icalendar = pkgs.callPackage ./calendar-cli/types-icalendar.nix {
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
          };
        };
    };
}
