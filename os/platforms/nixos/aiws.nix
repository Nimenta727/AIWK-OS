{ pkgs, modulesPath, aiwsUiSource ? null, ... }:
let
  core = pkgs.runCommand "aiws-guest-runtime" {} ''
    mkdir -p $out/lib/aiws
    cp ${../../runtime}/*.py $out/lib/aiws/
  '';
  ui = if aiwsUiSource == null
    then pkgs.runCommand "aiws-no-ui" {} "mkdir -p $out"
    else pkgs.runCommand "aiws-workbench-ui" {} ''
      mkdir -p $out
      cp -a ${aiwsUiSource}/. $out/
    '';
  workbench = pkgs.writeShellScriptBin "aiws-workbench" ''
    if [ "$(${pkgs.coreutils}/bin/id -u)" -eq 0 ]; then
      echo "AIWS workbench must not run as guest root" >&2
      exit 1
    fi
    exec ${pkgs.python3}/bin/python3 ${core}/lib/aiws/aiws_workbench.py "$@"
  '';
  toolctl = pkgs.writeShellScriptBin "aiws-toolctl" ''
    exec ${pkgs.python3}/bin/python3 ${core}/lib/aiws/aiws_mcp.py "$@"
  '';
  openWorkbench = pkgs.writeShellScriptBin "aiws-open-workbench" ''
    for i in $(${pkgs.coreutils}/bin/seq 1 45); do
      if ${pkgs.curl}/bin/curl --silent --fail --noproxy '*' --max-time 1 http://127.0.0.1:17640/api/v1/health >/dev/null; then
        exec ${pkgs.chromium}/bin/chromium --no-first-run --app=http://127.0.0.1:17640/
      fi
      ${pkgs.coreutils}/bin/sleep 1
    done
    echo "AIWS service did not respond" >&2
    exit 1
  '';
  probe = pkgs.writeShellScriptBin "aiws-boot-probe" ''
    set -eu
    ${pkgs.systemd}/bin/systemctl is-active --quiet display-manager
    ${pkgs.procps}/bin/pgrep -x xfce4-session >/dev/null
    ${pkgs.curl}/bin/curl --silent --fail --noproxy '*' --max-time 3 http://127.0.0.1:17640/api/v1/health |
      ${pkgs.python3}/bin/python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["uiBundled"] and x["guestOnly"]'
    ${toolctl}/bin/aiws-toolctl --list | ${pkgs.gnugrep}/bin/grep -q '"code.symbols"'
    echo "AIWS_BOOT_SMOKE_PASS: desktop=xfce workbench=active tools=mcp ui=react"
  '';
in {
  imports = [ (modulesPath + "/installer/cd-dvd/installation-cd-minimal.nix") ];
  networking.hostName = "aiws-os";
  environment.etc."aiws/guest-managed".text = "AIWS_GUEST_ONLY_VERSION=1\n";
  networking.networkmanager.enable = false;
  networking.firewall.enable = true;

  # Disposable offline VM profile ONLY. Never auto-login on a shared/online guest.
  users.users.aiws = { isNormalUser = true; description = "AIWS guest user"; };
  services.xserver.enable = true;
  services.xserver.displayManager.lightdm.enable = true;
  services.xserver.desktopManager.xfce.enable = true;
  services.displayManager.autoLogin.enable = true;
  services.displayManager.autoLogin.user = "aiws";
  services.displayManager.defaultSession = "xfce";

  environment.systemPackages = with pkgs; [
    workbench toolctl openWorkbench probe chromium firefox
    geany mousepad python3 nodejs_22 clang cmake git
    ripgrep go rustc cargo curl
  ];
  environment.etc."xdg/autostart/aiws-workbench.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=AIWS OS Workbench
    Exec=${openWorkbench}/bin/aiws-open-workbench
    Terminal=false
    OnlyShowIn=XFCE;
    X-GNOME-Autostart-enabled=true
  '';

  systemd.user.services.aiws-workbench = {
    description = "AIWS guest-only workbench controller";
    wantedBy = [ "default.target" ];
    environment.AIWS_UI_DIR = "${ui}";
    serviceConfig = {
      ExecStart = "${workbench}/bin/aiws-workbench";
      Restart = "on-failure";
      RestartSec = 3;
      NoNewPrivileges = true;
      PrivateTmp = true;
      UMask = "0077";
    };
  };
  systemd.services.aiws-boot-smoke = {
    description = "AIWS OS boot integration receipt";
    wantedBy = [ "multi-user.target" ];
    after = [ "display-manager.service" ];
    serviceConfig = {
      Type = "oneshot";
      TimeoutStartSec = 300;
      StandardOutput = "journal+console";
      StandardError = "journal+console";
      ExecStart = "${pkgs.writeShellScript "aiws-probe-delay" ''
        ${pkgs.coreutils}/bin/sleep 70
        exec ${probe}/bin/aiws-boot-probe
      ''}";
    };
  };
  system.stateVersion = "26.05";
}
