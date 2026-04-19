{ self, lib, ... }:
let
  registry = import ./skills.nix;

  # Base module for one package: installs the CLI and symlinks its skill dir
  # into every configured agent skills directory. Carries a stable `key` so the
  # module system deduplicates it when imported multiple times (e.g. directly
  # *and* via a variant like `browser-cli-with-extension`).
  mkBaseModule =
    pkgName:
    { pkgs, config, ... }:
    let
      pkg = self.packages.${pkgs.stdenv.hostPlatform.system}.${pkgName};
      skillDir = "${pkg}/share/skills/${pkgName}";
    in
    {
      key = "mics-skills/base/${pkgName}";
      home.packages = [ pkg ];
      home.file = lib.listToAttrs (
        map (
          dir: lib.nameValuePair "${dir}/${pkgName}" { source = skillDir; }
        ) config.programs.mics-skills.skillDirs
      );
    };

  mkSkillModule =
    name: def:
    let
      pkgName = def.package or name;
      extra = def.extra or (_: { });
    in
    {
      key = "mics-skills/${name}";
      imports = [
        ./home-manager-common.nix
        (mkBaseModule pkgName)
        (extra { inherit self; })
      ];
    };
in
{
  flake.homeModules = builtins.mapAttrs mkSkillModule registry;
}
