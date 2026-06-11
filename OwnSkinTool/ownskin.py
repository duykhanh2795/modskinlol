import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional


APP_NAME = "OwnSkinTool"
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
MODS_DIR = DATA_DIR / "mods"
PACKAGES_DIR = DATA_DIR / "packages"
LICENSES_DIR = DATA_DIR / "licenses"
INJECTION_DIR = DATA_DIR / "injection"
INJECTION_MODS_DIR = INJECTION_DIR / "mods"
OVERLAY_DIR = INJECTION_DIR / "overlay"
LOGS_DIR = DATA_DIR / "logs"
CONFIG_PATH = DATA_DIR / "config.json"
CACHE_INDEX_PATH = DATA_DIR / "cached_skins_index.json"
RUNOVERLAY_CONFIG = INJECTION_DIR / "runoverlay.config"
PID_PATH = INJECTION_DIR / "runoverlay.pid"
MONITOR_PID_PATH = INJECTION_DIR / "monitor.pid"


DEFAULT_CONFIG = {
    "game_path": "",
    "client_path": "",
    "mod_tools": "",
    "pengu_loader": "",
    "pengu_dir": "",
    "vendor_secret": "",
    "vendor_private_key": {},
    "vendor_public_key": {},
}


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{now()} | {message}"
    print(line)
    with (LOGS_DIR / "ownskin.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def ensure_dirs() -> None:
    for path in (DATA_DIR, MODS_DIR, PACKAGES_DIR, LICENSES_DIR, INJECTION_MODS_DIR, OVERLAY_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)
    if not RUNOVERLAY_CONFIG.exists():
        RUNOVERLAY_CONFIG.write_text("[General]\n", encoding="utf-8")


def read_ini_value(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";", "[")) or "=" not in line:
            continue
        k, value = line.split("=", 1)
        if k.strip().lower() == key.lower():
            return value.strip()
    return ""


def auto_detect_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()

    old_cfg = Path(os.environ.get("LOCALAPPDATA", "")) / "modskinlol" / "config.ini"
    league_path = read_ini_value(old_cfg, "leaguepath")
    client_path = read_ini_value(old_cfg, "clientpath")
    if league_path:
        cfg["game_path"] = league_path
    if client_path:
        cfg["client_path"] = client_path

    bundled_tools = ROOT.parent / "Modskinlol" / "_internal" / "injection" / "tools" / "mod-tools.exe"
    if bundled_tools.exists():
        cfg["mod_tools"] = str(bundled_tools)

    bundled_pengu = ROOT.parent / "Modskinlol" / "_internal" / "Pengu Loader" / "Pengu Loader.exe"
    if bundled_pengu.exists():
        cfg["pengu_loader"] = str(bundled_pengu)
        cfg["pengu_dir"] = str(bundled_pengu.parent)

    return cfg


def load_config() -> dict:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        cfg = auto_detect_config()
        cfg["vendor_secret"] = secrets.token_hex(32)
        private_key, public_key = generate_rsa_keypair()
        cfg["vendor_private_key"] = private_key
        cfg["vendor_public_key"] = public_key
        save_config(cfg)
        return cfg
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    detected = auto_detect_config()
    changed = False
    for key, value in detected.items():
        if not cfg.get(key) and value:
            cfg[key] = value
            changed = True
    if not cfg.get("vendor_secret"):
        cfg["vendor_secret"] = secrets.token_hex(32)
        changed = True
    if not cfg.get("vendor_private_key") or not cfg.get("vendor_public_key"):
        private_key, public_key = generate_rsa_keypair()
        cfg["vendor_private_key"] = private_key
        cfg["vendor_public_key"] = public_key
        changed = True
    if changed:
        save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    ensure_dirs()
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def require_file(path: str, label: str) -> Path:
    value = Path(path) if path else Path()
    if not value.exists() or not value.is_file():
        raise SystemExit(f"{label} is missing or invalid: {path!r}")
    return value


def require_dir(path: str, label: str) -> Path:
    value = Path(path) if path else Path()
    if not value.exists() or not value.is_dir():
        raise SystemExit(f"{label} is missing or invalid: {path!r}")
    return value


def safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in name.strip())
    cleaned = cleaned.strip("._")
    if not cleaned:
        raise SystemExit("Mod name cannot be empty.")
    return cleaned


def is_probable_prime(n: int) -> bool:
    if n < 2:
        return False
    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]
    for p in small_primes:
        if n == p:
            return True
        if n % p == 0:
            return False
    d = n - 1
    s = 0
    while d % 2 == 0:
        s += 1
        d //= 2
    for a in [2, 325, 9375, 28178, 450775, 9780504, 1795265022]:
        if a % n == 0:
            continue
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def generate_prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(candidate):
            return candidate


def generate_rsa_keypair(bits: int = 2048) -> tuple[dict, dict]:
    e = 65537
    while True:
        p = generate_prime(bits // 2)
        q = generate_prime(bits // 2)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if phi % e != 0:
            break
    n = p * q
    d = pow(e, -1, phi)
    private_key = {"n": str(n), "e": str(e), "d": str(d)}
    public_key = {"n": str(n), "e": str(e)}
    return private_key, public_key


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def get_machine_id() -> str:
    parts = [
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERNAME", ""),
        os.environ.get("PROCESSOR_IDENTIFIER", ""),
        os.environ.get("PROCESSOR_ARCHITECTURE", ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8", errors="ignore")).hexdigest()[:32]


def manifest_path(mod_name: str) -> Path:
    return MODS_DIR / safe_name(mod_name) / "ownskin.manifest.json"


def load_mod_manifest(mod_name: str) -> dict:
    return read_json(manifest_path(mod_name), {})


def canonical_json(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(payload: dict, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_json(payload), hashlib.sha256).hexdigest()


def rsa_sign_payload(payload: dict, private_key: dict) -> str:
    digest = hashlib.sha256(canonical_json(payload)).digest()
    value = int.from_bytes(digest, "big")
    signature = pow(value, int(private_key["d"]), int(private_key["n"]))
    return hex(signature)[2:]


def rsa_verify_payload(payload: dict, signature: str, public_key: dict) -> bool:
    try:
        digest = hashlib.sha256(canonical_json(payload)).digest()
        expected = int.from_bytes(digest, "big")
        actual = pow(int(signature, 16), int(public_key["e"]), int(public_key["n"]))
        return actual == expected
    except Exception:
        return False


def verify_license(mod_name: str) -> tuple[bool, str]:
    manifest = load_mod_manifest(mod_name)
    if not manifest.get("license_required"):
        return True, "license not required"

    license_path = LICENSES_DIR / f"{safe_name(mod_name)}.license.json"
    lic = read_json(license_path, {})
    payload = lic.get("payload")
    signature = lic.get("signature")
    if not payload or not signature:
        return False, f"missing license: {license_path}"

    cfg = load_config()
    if lic.get("algorithm") == "rsa-sha256":
        valid_signature = rsa_verify_payload(payload, signature, cfg["vendor_public_key"])
    else:
        expected = sign_payload(payload, cfg["vendor_secret"])
        valid_signature = hmac.compare_digest(signature, expected)
    if not valid_signature:
        return False, "license signature is invalid"
    if payload.get("mod") != safe_name(mod_name):
        return False, "license belongs to another mod"
    if payload.get("machine_id") and payload["machine_id"] != get_machine_id():
        return False, "license is for another machine"
    expires_at = payload.get("expires_at")
    if expires_at and time.strftime("%Y-%m-%d") > expires_at:
        return False, "license expired"
    return True, "license valid"


def run_capture(args: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    log("EXEC " + " ".join(f'"{a}"' if " " in a else a for a in args))
    proc = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if proc.stdout.strip():
        log("STDOUT " + proc.stdout.strip())
    if proc.stderr.strip():
        log("STDERR " + proc.stderr.strip())
    return proc


def windows_pid_running(pid: str) -> bool:
    if not pid or not pid.isdigit() or sys.platform != "win32":
        return False
    proc = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        text=True,
        capture_output=True,
    )
    return proc.returncode == 0 and pid in proc.stdout


def process_status() -> dict:
    overlay_pid = PID_PATH.read_text(encoding="utf-8").strip() if PID_PATH.exists() else ""
    monitor_pid = MONITOR_PID_PATH.read_text(encoding="utf-8").strip() if MONITOR_PID_PATH.exists() else ""
    overlay_running = windows_pid_running(overlay_pid)
    monitor_running = windows_pid_running(monitor_pid)
    if overlay_pid and not overlay_running:
        PID_PATH.unlink(missing_ok=True)
        overlay_pid = ""
    if monitor_pid and not monitor_running:
        MONITOR_PID_PATH.unlink(missing_ok=True)
        monitor_pid = ""
    return {
        "runoverlay_pid": overlay_pid,
        "runoverlay_running": overlay_running,
        "monitor_pid": monitor_pid,
        "monitor_running": monitor_running,
    }


def init_cmd(args: argparse.Namespace) -> None:
    cfg = load_config()
    changed = False
    if args.game_path:
        cfg["game_path"] = str(Path(args.game_path).resolve())
        changed = True
    if args.client_path:
        cfg["client_path"] = str(Path(args.client_path).resolve())
        changed = True
    if args.mod_tools:
        cfg["mod_tools"] = str(Path(args.mod_tools).resolve())
        changed = True
    if args.pengu_loader:
        pengu = Path(args.pengu_loader).resolve()
        cfg["pengu_loader"] = str(pengu)
        cfg["pengu_dir"] = str(pengu.parent)
        changed = True
    if changed:
        save_config(cfg)
    log(f"Initialized {APP_NAME}. Config: {CONFIG_PATH}")


def status_cmd(_args: argparse.Namespace) -> None:
    cfg = load_config()
    public_cfg = cfg.copy()
    public_cfg["vendor_secret"] = "<hidden>"
    public_cfg["vendor_private_key"] = "<hidden>"
    public_cfg["vendor_public_key"] = "<present>" if cfg.get("vendor_public_key") else "<missing>"
    print(json.dumps(public_cfg, indent=2))
    checks = {
        "game_path": Path(cfg["game_path"]).is_dir() if cfg["game_path"] else False,
        "mod_tools": Path(cfg["mod_tools"]).is_file() if cfg["mod_tools"] else False,
        "pengu_loader": Path(cfg["pengu_loader"]).is_file() if cfg["pengu_loader"] else False,
        "mods_count": len([p for p in MODS_DIR.iterdir() if p.is_dir()]),
        "machine_id": get_machine_id(),
    }
    checks.update(process_status())
    print(json.dumps(checks, indent=2))


def preflight_cmd(_args: argparse.Namespace) -> None:
    cfg = load_config()
    checks = {
        "game_path": Path(cfg["game_path"]).is_dir() if cfg["game_path"] else False,
        "mod_tools": Path(cfg["mod_tools"]).is_file() if cfg["mod_tools"] else False,
        "cache_root": cached_skin_root().is_dir(),
        "mods_dir": MODS_DIR.is_dir(),
        "overlay_dir": OVERLAY_DIR.is_dir(),
    }
    checks.update(process_status())
    for key, value in checks.items():
        if key.endswith("_running"):
            text = "RUNNING" if value else "STOPPED"
        elif key.endswith("_pid"):
            text = value or "-"
        else:
            text = "OK" if value is True else value if value else "MISSING"
        print(f"{key}: {text}")
    required = ["game_path", "mod_tools", "cache_root", "mods_dir", "overlay_dir"]
    failed = [key for key in required if not checks.get(key)]
    if failed:
        raise SystemExit("Preflight failed: " + ", ".join(failed))


def import_cmd(args: argparse.Namespace) -> None:
    load_config()
    src = Path(args.source).resolve()
    if not src.exists():
        raise SystemExit(f"Source not found: {src}")
    name = safe_name(args.name or src.stem)
    target = MODS_DIR / name
    if target.exists() and not args.force:
        raise SystemExit(f"Mod already exists: {name}. Use --force to replace it.")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    if src.is_dir():
        for child in src.iterdir():
            dst = target / child.name
            if child.is_dir():
                shutil.copytree(child, dst)
            else:
                shutil.copy2(child, dst)
    elif zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as zf:
            zf.extractall(target)
    else:
        raise SystemExit("Only directories and zip/fantome-style archives are supported.")

    manifest = {
        "name": name,
        "source": str(src),
        "imported_at": now(),
        "license_required": False,
    }
    package_manifest = target / "ownskin.package.json"
    if package_manifest.exists():
        package_data = read_json(package_manifest, {})
        manifest.update({
            "display_name": package_data.get("display_name") or package_data.get("name") or name,
            "version": package_data.get("version", "1.0.0"),
            "license_required": bool(package_data.get("license_required")),
            "package_id": package_data.get("package_id", name),
        })
    (target / "ownskin.manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Imported mod '{name}' into {target}")


def find_cached_skin_zip(skin_id: str) -> Path:
    skin_id = safe_name(str(skin_id))
    cache_root = cached_skin_root()
    if not cache_root.exists():
        raise SystemExit(f"Modskinlol skin cache not found: {cache_root}")
    matches = list(cache_root.rglob(f"{skin_id}.zip"))
    if not matches:
        raise SystemExit(f"Cached skin zip not found for skin ID {skin_id}")
    matches.sort(key=lambda p: (len(p.parts), str(p)))
    return matches[0]


def cached_skin_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "modskinlol" / "skins"


def resources_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "modskinlol" / "resources"


def load_skin_name_resources() -> dict[str, dict]:
    root = resources_root()
    names: dict[str, dict] = {}
    if not root.exists():
        return names
    for path in root.glob("*/skin_ids.json"):
        lang = path.parent.name.lower()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for skin_id, name in data.items():
            item = names.setdefault(str(skin_id), {"aliases": []})
            clean = str(name).strip()
            if not clean:
                continue
            item["aliases"].append(clean)
            if lang == "en":
                item["en"] = clean
            elif lang == "vi":
                item["vi"] = clean
            elif "default" not in item:
                item["default"] = clean
    return names


def cached_skin_info(zip_path: Path, resource_names: Optional[dict[str, dict]] = None) -> dict:
    skin_id = zip_path.stem
    resource = (resource_names or {}).get(skin_id, {})
    resource_name = resource.get("en") or resource.get("vi") or resource.get("default") or ""
    info = {
        "id": skin_id,
        "name": resource_name or f"Skin {skin_id}",
        "author": "",
        "aliases": sorted(set(resource.get("aliases") or [])),
        "path": str(zip_path),
    }
    try:
        with zipfile.ZipFile(zip_path) as zf:
            candidates = [name for name in zf.namelist() if name.replace("\\", "/").lower() == "meta/info.json"]
            if not candidates:
                return info
            data = json.loads(zf.read(candidates[0]).decode("utf-8-sig", errors="ignore"))
            meta_name = str(data.get("Name") or data.get("name") or "").strip()
            if meta_name:
                info["name"] = meta_name
                aliases = set(info.get("aliases") or [])
                aliases.add(meta_name)
                info["aliases"] = sorted(aliases)
            info["author"] = str(data.get("Author") or data.get("author") or "")
    except Exception as exc:
        info["error"] = str(exc)
    return info


def cached_skin_signature(paths: list[Path]) -> dict:
    latest = 0
    resource_paths = list(resources_root().glob("*/skin_ids.json"))
    for path in paths + resource_paths:
        try:
            latest = max(latest, int(path.stat().st_mtime))
        except OSError:
            continue
    return {"count": len(paths), "resources": len(resource_paths), "latest_mtime": latest, "index_version": 2}


def load_cached_skin_index(paths: list[Path]) -> list[dict]:
    signature = cached_skin_signature(paths)
    index = read_json(CACHE_INDEX_PATH, {})
    if index.get("signature") == signature:
        return list(index.get("skins") or [])

    resource_names = load_skin_name_resources()
    workers = min(32, max(4, (os.cpu_count() or 4) * 2))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        skins = list(pool.map(lambda path: cached_skin_info(path, resource_names), paths))
    skins.sort(key=lambda item: (item.get("name", "").lower(), item.get("id", "")))
    write_json(CACHE_INDEX_PATH, {"signature": signature, "skins": skins})
    return skins


def list_cached_skins(limit: int = 0, query: str = "") -> list[dict]:
    cache_root = cached_skin_root()
    if not cache_root.exists():
        raise SystemExit(f"Modskinlol skin cache not found: {cache_root}")
    paths = sorted(cache_root.rglob("*.zip"))
    skins = load_cached_skin_index(paths)
    query_lower = query.lower().strip()
    results = []
    for info in skins:
        aliases = " ".join(info.get("aliases") or [])
        haystack = f"{info.get('id', '')} {info.get('name', '')} {info.get('author', '')} {aliases}".lower()
        if query_lower and query_lower not in haystack:
            continue
        results.append(info)
        if limit and len(results) >= limit:
            break
    return results


def cache_list_cmd(args: argparse.Namespace) -> None:
    for skin in list_cached_skins(limit=args.limit, query=args.query or ""):
        print(f"{skin['id']}\t{skin['name']}\t{skin.get('author', '')}")


def cache_audit_cmd(_args: argparse.Namespace) -> None:
    skins = list_cached_skins()
    missing_name = [skin for skin in skins if skin.get("name") == f"Skin {skin.get('id')}"]
    missing_aliases = [skin for skin in skins if not skin.get("aliases")]
    errors = [skin for skin in skins if skin.get("error")]
    print(f"Cached skins: {len(skins)}")
    print(f"Missing display names: {len(missing_name)}")
    print(f"Missing aliases: {len(missing_aliases)}")
    print(f"Metadata read errors: {len(errors)}")
    if missing_name:
        print("Missing display name samples:")
        for skin in missing_name[:20]:
            print(f"{skin['id']}\t{skin.get('path', '')}")
    if errors:
        print("Metadata error samples:")
        for skin in errors[:20]:
            print(f"{skin['id']}\t{skin.get('error', '')}\t{skin.get('path', '')}")


def import_cache_cmd(args: argparse.Namespace) -> None:
    zip_path = find_cached_skin_zip(args.skin_id)
    name = args.name or f"skin_{safe_name(str(args.skin_id))}"
    log(f"Using cached skin package: {zip_path}")
    import_cmd(argparse.Namespace(source=str(zip_path), name=name, force=args.force))


def list_cmd(_args: argparse.Namespace) -> None:
    load_config()
    mods = sorted(p for p in MODS_DIR.iterdir() if p.is_dir())
    if not mods:
        print("No mods installed.")
        return
    for mod in mods:
        manifest = read_json(mod / "ownskin.manifest.json", {})
        suffix = " [licensed]" if manifest.get("license_required") else ""
        print(mod.name + suffix)


def clean_path(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def prepare_injection_mods(names: list[str]) -> list[str]:
    clean_path(INJECTION_MODS_DIR)
    prepared = []
    for raw_name in names:
        name = safe_name(raw_name)
        src = MODS_DIR / name
        if not src.exists() or not src.is_dir():
            raise SystemExit(f"Installed mod not found: {name}")
        ok, reason = verify_license(name)
        if not ok:
            raise SystemExit(f"License check failed for {name}: {reason}")
        dst = INJECTION_MODS_DIR / name
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("ownskin.manifest.json"))
        prepared.append(name)
    return prepared


def build_cmd(args: argparse.Namespace) -> None:
    cfg = load_config()
    mod_tools = require_file(cfg["mod_tools"], "mod_tools")
    game_path = require_dir(cfg["game_path"], "game_path")
    mod_names = prepare_injection_mods(args.mods)
    clean_path(OVERLAY_DIR)
    command = [
        str(mod_tools),
        "mkoverlay",
        str(INJECTION_MODS_DIR),
        str(OVERLAY_DIR),
        f"--game:{game_path}",
        "--mods:" + "/".join(mod_names),
        "--noTFT",
        "--ignoreConflict",
    ]
    proc = run_capture(command)
    if proc.returncode != 0:
        raise SystemExit(f"mkoverlay failed with exit code {proc.returncode}")
    log("Overlay built: " + str(OVERLAY_DIR))


def run_cmd(args: argparse.Namespace) -> None:
    cfg = load_config()
    mod_tools = require_file(cfg["mod_tools"], "mod_tools")
    game_path = require_dir(cfg["game_path"], "game_path")
    if args.mods:
        build_cmd(argparse.Namespace(mods=args.mods))
    if not any(OVERLAY_DIR.iterdir()):
        raise SystemExit("Overlay is empty. Run build first or pass mod names to run.")

    command = [
        str(mod_tools),
        "runoverlay",
        str(OVERLAY_DIR),
        str(RUNOVERLAY_CONFIG),
        f"--game:{game_path}",
        "--opts:configless",
    ]
    log("START " + " ".join(f'"{a}"' if " " in a else a for a in command))
    stdout = (LOGS_DIR / "runoverlay.stdout.log").open("ab")
    stderr = (LOGS_DIR / "runoverlay.stderr.log").open("ab")
    proc = subprocess.Popen(command, stdout=stdout, stderr=stderr)
    PID_PATH.write_text(str(proc.pid), encoding="utf-8")
    log(f"runoverlay started with PID {proc.pid}")


def run_classic_cmd(args: argparse.Namespace) -> None:
    cfg = load_config()
    mod_tools = require_file(cfg["mod_tools"], "mod_tools")
    game_path = require_dir(cfg["game_path"], "game_path")
    if args.mods:
        build_cmd(argparse.Namespace(mods=args.mods))
    if not any(OVERLAY_DIR.iterdir()):
        raise SystemExit("Overlay is empty. Run build first or pass mod names to run.")

    command = [
        str(mod_tools),
        "runoverlay",
        str(OVERLAY_DIR),
        str(RUNOVERLAY_CONFIG),
        f"--game:{game_path}",
        "--opts:configless",
    ]
    log("CLASSIC START " + " ".join(f'"{a}"' if " " in a else a for a in command))
    stdout = (LOGS_DIR / "runoverlay.stdout.log").open("ab")
    stderr = (LOGS_DIR / "runoverlay.stderr.log").open("ab")
    proc = subprocess.Popen(command, stdout=stdout, stderr=stderr)
    PID_PATH.write_text(str(proc.pid), encoding="utf-8")
    log(f"classic runoverlay started with PID {proc.pid}")


def stop_cmd(_args: argparse.Namespace) -> None:
    killed = 0
    if PID_PATH.exists():
        pid = PID_PATH.read_text(encoding="utf-8").strip()
        if pid:
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, text=True)
            killed += 1
        PID_PATH.unlink(missing_ok=True)

    ps = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object { $_.ProcessName -like '*mod-tools*' -or $_.ProcessName -like '*runoverlay*' } | Select-Object -ExpandProperty Id"],
        text=True,
        capture_output=True,
    )
    for line in ps.stdout.splitlines():
        pid = line.strip()
        if pid.isdigit():
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, text=True)
            killed += 1
    log(f"Stop requested. Kill attempts: {killed}")


def safe_stop_all_cmd(_args: argparse.Namespace) -> None:
    stop_cmd(argparse.Namespace())
    monitor_stop_cmd(argparse.Namespace())
    clean_path(OVERLAY_DIR)
    clean_path(INJECTION_MODS_DIR)
    log("Safe stop all completed.")


def safe_run_cache_cmd(args: argparse.Namespace) -> None:
    preflight_cmd(argparse.Namespace())
    skin_id = safe_name(str(args.skin_id))
    name = args.name or f"skin_{skin_id}"
    stop_cmd(argparse.Namespace())
    import_cache_cmd(argparse.Namespace(skin_id=skin_id, name=name, force=True))
    run_cmd(argparse.Namespace(mods=[name], stop_existing=False))


def pengu_cmd(args: argparse.Namespace) -> None:
    cfg = load_config()
    pengu = require_file(cfg["pengu_loader"], "pengu_loader")
    action = "--force-activate" if args.action == "activate" else "--force-deactivate"
    proc = run_capture([str(pengu), action, "--silent"])
    if proc.returncode != 0:
        raise SystemExit(f"Pengu Loader command failed with exit code {proc.returncode}")
    log(f"Pengu Loader {args.action} completed.")


def read_lcu_lockfile(client_path: str) -> Optional[dict]:
    candidates = []
    if client_path:
        candidates.append(Path(client_path) / "lockfile")
    candidates += [
        Path("C:/Riot Games/League of Legends/lockfile"),
        Path("C:/Program Files/Riot Games/League of Legends/lockfile"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore").strip()
            name, pid, port, password, protocol = raw.split(":", 4)
            return {
                "path": str(path),
                "name": name,
                "pid": pid,
                "port": port,
                "password": password,
                "protocol": protocol,
            }
        except Exception as exc:
            log(f"[LCU] Failed to read lockfile {path}: {exc}")
    return None


def lcu_request(lockfile: dict, endpoint: str):
    token = base64.b64encode(f"riot:{lockfile['password']}".encode("utf-8")).decode("ascii")
    url = f"https://127.0.0.1:{lockfile['port']}{endpoint}"
    request = urllib.request.Request(url, headers={
        "Authorization": "Basic " + token,
        "Accept": "application/json",
    })
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, context=context, timeout=2) as response:
        data = response.read()
    if not data:
        return None
    return json.loads(data.decode("utf-8", errors="replace"))


def find_local_player(session: dict) -> dict:
    local_cell_id = session.get("localPlayerCellId")
    for bucket in ("myTeam", "theirTeam"):
        for player in session.get(bucket, []) or []:
            if player.get("cellId") == local_cell_id:
                return player
    return {}


def read_champ_select_state(lockfile: dict) -> dict:
    state = {
        "phase": None,
        "champion_id": None,
        "skin_id": None,
        "is_locked": False,
    }
    try:
        state["phase"] = lcu_request(lockfile, "/lol-gameflow/v1/gameflow-phase")
    except Exception:
        return state

    if state["phase"] not in ("ChampSelect", "ReadyCheck", "InProgress", "GameStart", "WaitingForStats"):
        return state

    try:
        selector = lcu_request(lockfile, "/lol-champ-select/v1/skin-selector-info")
        if isinstance(selector, dict):
            if selector.get("selectedSkinId"):
                state["skin_id"] = int(selector["selectedSkinId"])
            if selector.get("championId"):
                state["champion_id"] = int(selector["championId"])
    except Exception:
        pass

    try:
        session = lcu_request(lockfile, "/lol-champ-select/v1/session")
        if isinstance(session, dict):
            player = find_local_player(session)
            if player:
                if player.get("championId"):
                    state["champion_id"] = int(player["championId"])
                if player.get("selectedSkinId"):
                    state["skin_id"] = int(player["selectedSkinId"])
                state["is_locked"] = bool(player.get("championId"))
    except Exception:
        pass

    return state


def auto_run_skin_id(skin_id: int, stop_existing: bool = True) -> None:
    mod_name = f"auto_skin_{skin_id}"
    if stop_existing:
        stop_cmd(argparse.Namespace())
    import_cache_cmd(argparse.Namespace(skin_id=str(skin_id), name=mod_name, force=True))
    run_cmd(argparse.Namespace(mods=[mod_name]))


def monitor_cmd(args: argparse.Namespace) -> None:
    cfg = load_config()
    log("[MONITOR] Started LCU monitor")
    last_phase = None
    last_skin_id = None
    last_champion_id = None
    injected_key = None
    in_progress_since = None

    while True:
        lockfile = read_lcu_lockfile(cfg.get("client_path", ""))
        if not lockfile:
            if last_phase != "NoClient":
                log("[MONITOR] League Client lockfile not found")
                last_phase = "NoClient"
            time.sleep(args.interval)
            continue

        try:
            state = read_champ_select_state(lockfile)
        except Exception as exc:
            log(f"[MONITOR] LCU read failed: {exc}")
            time.sleep(args.interval)
            continue

        phase = state.get("phase")
        skin_id = state.get("skin_id")
        champion_id = state.get("champion_id")

        if phase != last_phase:
            log(f"[MONITOR] Phase: {last_phase} -> {phase}")
            last_phase = phase
            if phase in ("Lobby", "Matchmaking", "ReadyCheck", "ChampSelect"):
                injected_key = None
                in_progress_since = None
                if args.stop_on_lobby and phase == "Lobby":
                    stop_cmd(argparse.Namespace())

        if skin_id and skin_id != last_skin_id:
            log(f"[MONITOR] Selected skin changed: {last_skin_id} -> {skin_id}")
            last_skin_id = skin_id
        if champion_id and champion_id != last_champion_id:
            log(f"[MONITOR] Champion changed: {last_champion_id} -> {champion_id}")
            last_champion_id = champion_id

        if phase == "InProgress" and args.auto_run:
            if in_progress_since is None:
                in_progress_since = time.time()
            ready = time.time() - in_progress_since >= args.threshold
            key = f"{champion_id}:{skin_id}"
            if ready and skin_id and key != injected_key:
                log(f"[MONITOR] Auto-running skin {skin_id}")
                try:
                    auto_run_skin_id(int(skin_id), stop_existing=args.stop_existing)
                    injected_key = key
                except Exception as exc:
                    log(f"[MONITOR] Auto-run failed for skin {skin_id}: {exc}")
        elif phase != "InProgress":
            in_progress_since = None

        time.sleep(args.interval)


def monitor_start_cmd(args: argparse.Namespace) -> None:
    if MONITOR_PID_PATH.exists():
        pid = MONITOR_PID_PATH.read_text(encoding="utf-8").strip()
        if pid:
            log(f"[MONITOR] PID file already exists: {pid}")
            return
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "monitor",
        "--auto-run",
        "--interval",
        str(args.interval),
        "--threshold",
        str(args.threshold),
    ]
    if args.stop_on_lobby:
        command.append("--stop-on-lobby")
    stdout = (LOGS_DIR / "monitor.stdout.log").open("ab")
    stderr = (LOGS_DIR / "monitor.stderr.log").open("ab")
    proc = subprocess.Popen(command, cwd=str(ROOT.parent), stdout=stdout, stderr=stderr)
    MONITOR_PID_PATH.write_text(str(proc.pid), encoding="utf-8")
    log(f"[MONITOR] Started background monitor PID {proc.pid}")


def monitor_stop_cmd(_args: argparse.Namespace) -> None:
    if not MONITOR_PID_PATH.exists():
        log("[MONITOR] No monitor PID file found")
        return
    pid = MONITOR_PID_PATH.read_text(encoding="utf-8").strip()
    if pid:
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, text=True)
        log(f"[MONITOR] Stop requested for PID {pid}")
    MONITOR_PID_PATH.unlink(missing_ok=True)


def package_cmd(args: argparse.Namespace) -> None:
    load_config()
    name = safe_name(args.mod)
    src = MODS_DIR / name
    if not src.exists():
        raise SystemExit(f"Installed mod not found: {name}")

    manifest = load_mod_manifest(name)
    package_meta = {
        "package_id": args.package_id or manifest.get("package_id") or name,
        "name": name,
        "display_name": args.display_name or manifest.get("display_name") or name,
        "version": args.version,
        "license_required": bool(args.license_required),
        "created_at": now(),
    }
    manifest.update(package_meta)
    write_json(src / "ownskin.manifest.json", manifest)
    write_json(src / "ownskin.package.json", package_meta)

    output = Path(args.output).resolve() if args.output else PACKAGES_DIR / f"{name}-{args.version}.ownskin.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in src.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(src).as_posix())
    log(f"Package created: {output}")


def machine_id_cmd(_args: argparse.Namespace) -> None:
    print(get_machine_id())


def license_create_cmd(args: argparse.Namespace) -> None:
    cfg = load_config()
    mod_name = safe_name(args.mod)
    payload = {
        "mod": mod_name,
        "buyer": args.buyer,
        "issued_at": time.strftime("%Y-%m-%d"),
        "expires_at": args.expires_at or "",
        "machine_id": args.machine_id or "",
    }
    lic = {
        "algorithm": "rsa-sha256",
        "payload": payload,
        "signature": rsa_sign_payload(payload, cfg["vendor_private_key"]),
    }
    output = Path(args.output).resolve() if args.output else LICENSES_DIR / f"{mod_name}.license.json"
    write_json(output, lic)
    log(f"License created: {output}")


def license_activate_cmd(args: argparse.Namespace) -> None:
    path = Path(args.license_file).resolve()
    if not path.exists():
        raise SystemExit(f"License file not found: {path}")
    lic = read_json(path, {})
    payload = lic.get("payload") or {}
    mod_name = safe_name(args.mod or payload.get("mod", ""))
    if not mod_name:
        raise SystemExit("License file has no mod name. Pass --mod explicitly.")
    target = LICENSES_DIR / f"{mod_name}.license.json"
    shutil.copy2(path, target)
    ok, reason = verify_license(mod_name)
    if not ok:
        raise SystemExit(f"License activation failed: {reason}")
    log(f"License activated for {mod_name}: {target}")


def vendor_public_key_cmd(args: argparse.Namespace) -> None:
    cfg = load_config()
    output = Path(args.output).resolve() if args.output else DATA_DIR / "vendor_public_key.json"
    write_json(output, cfg["vendor_public_key"])
    log(f"Vendor public key exported: {output}")


def vendor_public_key_import_cmd(args: argparse.Namespace) -> None:
    path = Path(args.public_key_file).resolve()
    if not path.exists():
        raise SystemExit(f"Public key file not found: {path}")
    public_key = read_json(path, {})
    if not public_key.get("n") or not public_key.get("e"):
        raise SystemExit("Invalid public key file.")
    cfg = load_config()
    cfg["vendor_public_key"] = public_key
    save_config(cfg)
    log(f"Vendor public key imported: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ownskin", description="Local-only League mod overlay manager.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create/update local config.")
    p.add_argument("--game-path")
    p.add_argument("--client-path")
    p.add_argument("--mod-tools")
    p.add_argument("--pengu-loader")
    p.set_defaults(func=init_cmd)

    p = sub.add_parser("status", help="Show config and readiness checks.")
    p.set_defaults(func=status_cmd)

    p = sub.add_parser("preflight", help="Check local readiness before running a mod.")
    p.set_defaults(func=preflight_cmd)

    p = sub.add_parser("import", help="Import a mod directory or zip/fantome archive.")
    p.add_argument("source")
    p.add_argument("--name")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=import_cmd)

    p = sub.add_parser("import-cache", help="Import a skin package from the local Modskinlol skin cache by skin ID.")
    p.add_argument("skin_id")
    p.add_argument("--name")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=import_cache_cmd)

    p = sub.add_parser("safe-run-cache", help="Preflight, stop existing overlay, import cached skin, then run it.")
    p.add_argument("skin_id")
    p.add_argument("--name")
    p.set_defaults(func=safe_run_cache_cmd)

    p = sub.add_parser("cache-list", help="List locally cached skins by ID and name.")
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cache_list_cmd)

    p = sub.add_parser("cache-audit", help="Check cached skins for missing searchable names.")
    p.set_defaults(func=cache_audit_cmd)

    p = sub.add_parser("list", help="List installed local mods.")
    p.set_defaults(func=list_cmd)

    p = sub.add_parser("build", help="Build an overlay from installed mods.")
    p.add_argument("mods", nargs="+")
    p.set_defaults(func=build_cmd)

    p = sub.add_parser("run", help="Build optionally, then start runoverlay.")
    p.add_argument("mods", nargs="*")
    p.set_defaults(func=run_cmd)

    p = sub.add_parser("run-classic", help="Original run flow: build optionally, start runoverlay, return immediately.")
    p.add_argument("mods", nargs="*")
    p.set_defaults(func=run_classic_cmd)

    p = sub.add_parser("stop", help="Stop the active overlay process.")
    p.set_defaults(func=stop_cmd)

    p = sub.add_parser("safe-stop-all", help="Stop overlay and monitor, then clear generated overlay folders.")
    p.set_defaults(func=safe_stop_all_cmd)

    p = sub.add_parser("pengu", help="Activate or deactivate Pengu Loader.")
    p.add_argument("action", choices=("activate", "deactivate"))
    p.set_defaults(func=pengu_cmd)

    p = sub.add_parser("monitor", help="Foreground LCU monitor; can auto-run selected cached skin on game start.")
    p.add_argument("--auto-run", action="store_true")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--threshold", type=float, default=0.8)
    p.add_argument("--stop-existing", action="store_true", default=True)
    p.add_argument("--no-stop-existing", action="store_false", dest="stop_existing")
    p.add_argument("--stop-on-lobby", action="store_true")
    p.set_defaults(func=monitor_cmd)

    p = sub.add_parser("monitor-start", help="Start background LCU monitor.")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--threshold", type=float, default=0.8)
    p.add_argument("--stop-on-lobby", action="store_true")
    p.set_defaults(func=monitor_start_cmd)

    p = sub.add_parser("monitor-stop", help="Stop background LCU monitor.")
    p.set_defaults(func=monitor_stop_cmd)

    p = sub.add_parser("package", help="Create a distributable OwnSkin package from an installed mod.")
    p.add_argument("mod")
    p.add_argument("--output")
    p.add_argument("--display-name")
    p.add_argument("--package-id")
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--license-required", action="store_true")
    p.set_defaults(func=package_cmd)

    p = sub.add_parser("machine-id", help="Print this machine's local license id.")
    p.set_defaults(func=machine_id_cmd)

    p = sub.add_parser("license-create", help="Create a license for one of your packages.")
    p.add_argument("mod")
    p.add_argument("--buyer", required=True)
    p.add_argument("--machine-id")
    p.add_argument("--expires-at", help="YYYY-MM-DD. Omit for no expiry.")
    p.add_argument("--output")
    p.set_defaults(func=license_create_cmd)

    p = sub.add_parser("license-activate", help="Install a license file locally.")
    p.add_argument("license_file")
    p.add_argument("--mod")
    p.set_defaults(func=license_activate_cmd)

    p = sub.add_parser("vendor-public-key", help="Export the public key used to verify your licenses.")
    p.add_argument("--output")
    p.set_defaults(func=vendor_public_key_cmd)

    p = sub.add_parser("vendor-public-key-import", help="Import a vendor public key for license verification.")
    p.add_argument("public_key_file")
    p.set_defaults(func=vendor_public_key_import_cmd)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
