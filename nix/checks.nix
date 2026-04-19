{
  lib,
  packages,
  treefmtCheck,
}:
let
  packageChecks = lib.mapAttrs' (n: lib.nameValuePair "package-${n}") packages;
in
packageChecks // { treefmt = treefmtCheck; }
