{
  description = "LLM-useful CLI tools and skills";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    treefmt-nix.url = "github:numtide/treefmt-nix";
    treefmt-nix.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    {
      self,
      nixpkgs,
      treefmt-nix,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      lib = nixpkgs.lib;

      eachSystem =
        f:
        lib.genAttrs systems (
          system:
          f {
            inherit system;
            pkgs = nixpkgs.legacyPackages.${system};
          }
        );

      treefmtEval = eachSystem (
        { pkgs, ... }: treefmt-nix.lib.evalModule pkgs (import ./nix/treefmt.nix { inherit pkgs; })
      );
    in
    {
      packages = eachSystem ({ pkgs, ... }: pkgs.callPackages ./nix/packages.nix { });

      checks = eachSystem (
        { system, ... }:
        import ./nix/checks.nix {
          inherit lib;
          packages = self.packages.${system};
          treefmtCheck = treefmtEval.${system}.config.build.check self;
        }
      );

      formatter = eachSystem ({ system, ... }: treefmtEval.${system}.config.build.wrapper);

      homeModules = import ./nix/home-modules.nix { inherit self lib; } // {
        default = import ./nix/home-manager.nix;
      };

      homeManagerModules = {
        default = throw ''
          mics-skills: `homeManagerModules` has been removed.
          Use `homeModules.default` (legacy programs.mics-skills option module)
          or the per-skill modules `homeModules.<skill>` instead.
        '';
      };
    };
}
