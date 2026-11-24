"""Build the portable VaultSafe ZIP from the project source on Windows x64."""

from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "vaultsafe" / "assets"
PACKAGE_NAME = "VaultSafe-Windows-x64"
LOCAL_DATA_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".vaultsafe", ".vaultkey", ".csv", ".key"}


def build_binaries(work):
    icon = work / "VaultSafe.ico"
    with Image.open(ASSETS / "logo.png") as logo:
        logo.save(icon, sizes=[(16, 16), (32, 32), (48, 48), (128, 128), (256, 256)])
    output = work / "binaries"
    base = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--noupx", "--log-level", "WARN",
        "--paths", str(ROOT), "--icon", str(icon), "--distpath", str(output),
        "--workpath", str(work / "work"), "--specpath", str(work / "spec"),
    ]
    subprocess.run([
        *base, "--onedir", "--windowed", "--name", "VaultSafe",
        "--add-data", f"{ASSETS}:vaultsafe/assets",
        "--collect-data", "customtkinter", "--collect-data", "tldextract",
        "--copy-metadata", "tldextract", "main.py",
    ], cwd=ROOT, check=True)
    subprocess.run([
        *base, "--onedir", "--console", "--name", "VaultSafeChromeHost", "native_host/host.py",
    ], cwd=ROOT, check=True)
    subprocess.run([
        *base, "--onefile", "--windowed", "--name", "Thiet-lap-Chrome", "setup_chrome.py",
    ], cwd=ROOT, check=True)
    return output


def assemble_package(work, binaries):
    package = work / PACKAGE_NAME
    shutil.move(binaries / "VaultSafe", package)
    shutil.move(binaries / "Thiet-lap-Chrome.exe", package / "Thiet-lap-Chrome.exe")
    host = package / "native_host"
    host.mkdir()
    shutil.move(binaries / "VaultSafeChromeHost", host / "VaultSafeChromeHost")
    extension = package / "chrome_extension"
    extension.mkdir()
    for source in sorted((ROOT / "chrome_extension").iterdir()):
        if source.is_file() and (source.suffix in {".js", ".html", ".css", ".png"}
                                 or source.name == "manifest.json"):
            shutil.copy2(source, extension / source.name)
    shutil.copy2(Path(__file__).with_name("HUONG-DAN.txt"), package)
    return package


def write_zip(package, destination):
    with NamedTemporaryFile(dir=destination.parent, suffix=".zip", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=5) as archive:
            for file in sorted(package.rglob("*")):
                if not file.is_file():
                    continue
                if (file.suffix.lower() in LOCAL_DATA_SUFFIXES or file.name.startswith(("vaultsafe.db", ".env"))
                        or file.name == "security_preferences.json"):
                    raise RuntimeError(f"Unexpected local data in package: {file.relative_to(package)}")
                archive.write(file, file.relative_to(package.parent).as_posix())
        with ZipFile(temporary) as archive:
            invalid = archive.testzip()
            if invalid:
                raise RuntimeError(f"Invalid ZIP member: {invalid}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"} or sys.maxsize <= 2**32:
        raise SystemExit("Build this package with 64-bit Python on Windows x64.")
    output = ROOT / "dist"
    if output.resolve() != output:
        raise SystemExit("dist must be a local folder inside the project.")
    output.mkdir(exist_ok=True)
    destination = output / f"{PACKAGE_NAME}.zip"
    with TemporaryDirectory(prefix="vaultsafe-build-") as directory:
        work = Path(directory)
        package = assemble_package(work, build_binaries(work))
        write_zip(package, destination)
    print(destination)


if __name__ == "__main__":
    main()
