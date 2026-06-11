# OwnSkinTool

OwnSkinTool is a local-only overlay manager for League mod packages. It does not use
Modskinlol servers, analytics, keys, or remote feature flags.

This is a clean-room tool. It does not patch or bypass Modskinlol.

## What It Does

- Imports local mod archives or folders into `OwnSkinTool/data/mods`.
- Builds an overlay with `mod-tools.exe mkoverlay`.
- Starts the overlay with `mod-tools.exe runoverlay`.
- Stops the active overlay process.
- Can call Pengu Loader activate/deactivate if you point it at a Pengu Loader build.
- Creates `.ownskin.zip` packages for your own mods.
- Creates and activates signed local licenses for packages you sell.
- Includes a simple Windows GUI.
- Writes logs to `OwnSkinTool/data/logs`.

## GUI

Open without a terminal window:

```powershell
.\OwnSkinTool\OwnSkinTool.pyw
```

Old batch launcher:

```powershell
.\OwnSkinTool\gui.bat
```

The GUI can save paths, import mods, build/run/stop, activate/deactivate Pengu Loader,
create packages, create licenses, and activate customer license files.

Fast manual use:

1. Open `.\OwnSkinTool\OwnSkinTool.pyw`.
2. Click `Skin Browser`.
3. Search by skin name, champion name, author, or ID.
4. Select a skin and click `Run Selected`.

The tool imports that cached package as `skin_<id>` and starts it automatically.
If you already know the ID, click `Quick Run ID` and enter it directly.

`Run Selected` uses the original flow: import the cached skin, build the overlay, then
start `runoverlay`. `Safe Run` is only a stricter diagnostic flow. These are stability
modes; neither is anti-cheat bypassing and neither can guarantee account safety.

You can also double-click:

```powershell
.\OwnSkinTool\quick_run_cache.bat
```

Then enter the cached skin ID when asked.

## First Run

From `F:\modskinlol`:

```powershell
python .\OwnSkinTool\ownskin.py init
python .\OwnSkinTool\ownskin.py status
```

The init command auto-detects existing League and tool paths from this machine where possible.
If detection is wrong, set paths explicitly:

```powershell
python .\OwnSkinTool\ownskin.py init `
  --game-path "F:\Riot Games\League of Legends\Game" `
  --client-path "F:\Riot Games\League of Legends" `
  --mod-tools "F:\modskinlol\Modskinlol\_internal\injection\tools\mod-tools.exe" `
  --pengu-loader "F:\modskinlol\Modskinlol\_internal\Pengu Loader\Pengu Loader.exe"
```

## Import Mods

```powershell
python .\OwnSkinTool\ownskin.py import "D:\mods\MyMod.zip" --name my_mod
python .\OwnSkinTool\ownskin.py list
```

You can also import an extracted mod folder:

```powershell
python .\OwnSkinTool\ownskin.py import "D:\mods\MyExtractedMod" --name my_mod
```

## Import From Local Modskinlol Cache

If `C:\Users\<you>\AppData\Local\modskinlol\skins` contains cached skin packages,
you can import one by skin ID:

```powershell
python .\OwnSkinTool\ownskin.py import-cache 39037 --name mythmaker_irelia
python .\OwnSkinTool\ownskin.py run mythmaker_irelia
```

To search the local cache from the terminal:

```powershell
python .\OwnSkinTool\ownskin.py cache-list --query irelia
```

To audit whether cached skins have searchable names:

```powershell
python .\OwnSkinTool\ownskin.py cache-audit
```

Local readiness check:

```powershell
python .\OwnSkinTool\ownskin.py preflight
```

Stop overlay, monitor, and clear generated overlay folders:

```powershell
python .\OwnSkinTool\ownskin.py safe-stop-all
```

These cache packages contain `WAD/*.wad.client` plus `META/info.json`, so they can be
used by the overlay toolchain. Use them only where you have the right to use the
underlying assets; do not resell Riot or third-party assets you do not own.

## Build And Run

Build an overlay:

```powershell
python .\OwnSkinTool\ownskin.py build my_mod
```

Start the overlay:

```powershell
python .\OwnSkinTool\ownskin.py run
```

Build and run in one command:

```powershell
python .\OwnSkinTool\ownskin.py run my_mod
```

Stop overlay:

```powershell
python .\OwnSkinTool\ownskin.py stop
```

## Auto Run From Champ Select

OwnSkinTool can now monitor the League Client LCU locally. It remembers the selected
skin ID from Champ Select and, when the game reaches `InProgress`, imports the matching
cached skin package and starts the overlay automatically.

Start background monitor:

```powershell
python .\OwnSkinTool\ownskin.py monitor-start --stop-on-lobby
```

Stop background monitor:

```powershell
python .\OwnSkinTool\ownskin.py monitor-stop
```

Run monitor in the foreground for debugging:

```powershell
python .\OwnSkinTool\ownskin.py monitor --auto-run --stop-on-lobby
```

GUI buttons:

- `Monitor On`: starts the background monitor.
- `Monitor Off`: stops it.

The monitor requires League Client to be open so it can read the local `lockfile`.
It does not add a skin picker inside the League Client yet; it uses the skin ID that
the client currently reports.

## Pengu Loader

Activate:

```powershell
python .\OwnSkinTool\ownskin.py pengu activate
```

Deactivate:

```powershell
python .\OwnSkinTool\ownskin.py pengu deactivate
```

## Packaging Your Own Mods

Create a package from an installed mod:

```powershell
python .\OwnSkinTool\ownskin.py package my_mod --version 1.0.0 --license-required
```

The package will be written to `OwnSkinTool/data/packages` unless you pass `--output`.

Export your vendor public key:

```powershell
python .\OwnSkinTool\ownskin.py vendor-public-key --output vendor_public_key.json
```

Keep `OwnSkinTool/data/config.json` private on your seller machine because it contains the
private key used to sign licenses. Give customers only:

- Your packaged mod `.ownskin.zip`
- Your `vendor_public_key.json`
- Their license file

On a customer machine:

```powershell
python .\OwnSkinTool\ownskin.py vendor-public-key-import vendor_public_key.json
python .\OwnSkinTool\ownskin.py import "my_mod-1.0.0.ownskin.zip" --name my_mod
python .\OwnSkinTool\ownskin.py license-activate "my_mod.license.json"
python .\OwnSkinTool\ownskin.py run my_mod
```

Create a license:

```powershell
python .\OwnSkinTool\ownskin.py license-create my_mod --buyer customer_name --output my_mod.license.json
```

Bind to one machine:

```powershell
python .\OwnSkinTool\ownskin.py machine-id
python .\OwnSkinTool\ownskin.py license-create my_mod --buyer customer_name --machine-id CUSTOMER_MACHINE_ID --output my_mod.license.json
```

This is offline licensing. It is useful for basic distribution, but any fully local licensing
can be bypassed by a determined attacker who edits the program.

## Patch Updates

League patches can break any mod toolchain. OwnSkinTool keeps your workflow local, but it cannot
guarantee compatibility with future Riot patches. When patches break WAD hashes or asset paths,
update `mod-tools.exe` / `hashes.game.txt` from a source you control, then rebuild the overlay.

## Boundaries

OwnSkinTool does not:

- Clone Modskinlol backend logic.
- Bypass keys, licenses, or remote controls.
- Guarantee safety against Riot enforcement.
- Download private updates automatically.
- Provide unbreakable DRM.
