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
        "x86_64-darwin"
      ];

      imports = [
        inputs.treefmt-nix.flakeModule
      ];

      perSystem =
        { pkgs, ... }:
        {
          packages = {
            browser-cli = pkgs.python3.pkgs.callPackage ./browser-cli { };
            browser-cli-extension = (pkgs.callPackages ./firefox-extensions { }).browser-cli-extension;
            db-cli = pkgs.callPackage ./db-cli { };
            gmaps-cli = pkgs.python3.pkgs.callPackage ./gmaps-cli { };
            kagi-search = pkgs.python3.pkgs.callPackage ./kagi-search { };
            pexpect-cli = pkgs.callPackage ./pexpect-cli { };
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
              "browser-cli" = {
                extraPythonPackages = with pkgs.python3.pkgs; [
                  websockets
                ];
              };
              "kagi-search" = {
                extraPythonPackages = with pkgs.python3.pkgs; [
                  beautifulsoup4
                  types-beautifulsoup4
                ];
              };
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
