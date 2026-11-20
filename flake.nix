{
  description = "AIWS OS modular image targets";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      dist = builtins.getEnv "AIWS_UI_DIST";
      ui = if dist == "" then null else builtins.path { path = dist; name = "aiws-react-dist"; };
    in {
      nixosConfigurations.aiws-live = nixpkgs.lib.nixosSystem {
        inherit system;
        specialArgs = { aiwsUiSource = ui; };
        modules = [ ./os/platforms/nixos/aiws.nix ];
      };
      packages.${system}.aiws-iso = self.nixosConfigurations.aiws-live.config.system.build.isoImage;
    };
}
