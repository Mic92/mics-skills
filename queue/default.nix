{
  rustPlatform,
  lib,
  makeWrapper,
  pueue,
}:

rustPlatform.buildRustPackage {
  pname = "queue";
  version = "0.1.0";

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./Cargo.toml
      ./Cargo.lock
      ./src
      ./skill
    ];
  };

  cargoLock.lockFile = ./Cargo.lock;

  nativeBuildInputs = [ makeWrapper ];

  postInstall = ''
    mkdir -p $out/share/skills
    cp -r $src/skill $out/share/skills/queue
  '';
  # auto-start the daemon without requiring pueue on the user's PATH
  postFixup = ''
    wrapProgram $out/bin/queue \
      --set-default QUEUE_PUEUED ${lib.getExe' pueue "pueued"}
  '';

  meta = {
    description = "Agent-friendly frontend for pueue";
    mainProgram = "queue";
    license = lib.licenses.mit;
  };
}
