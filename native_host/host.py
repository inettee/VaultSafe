"""Chrome stdio host. Chrome sends one framed request per process."""

from pathlib import Path
import struct
import sys


# The launcher uses isolated mode, so add only the project's own import path.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vaultsafe.browser_protocol import MAX_MESSAGE, decode_message, encode_message, valid_request
from vaultsafe.chrome_registration import EXTENSION_ORIGIN


LENGTH = struct.Struct("<I")


def read_request(stream):
    header = stream.read(LENGTH.size)
    if len(header) != LENGTH.size:
        raise ValueError("Invalid native message header")
    size, = LENGTH.unpack(header)
    if not 0 < size <= MAX_MESSAGE:
        raise ValueError("Invalid native message size")
    payload = stream.read(size)
    if len(payload) != size:
        raise ValueError("Incomplete native message")
    return decode_message(payload)


def main():
    if getattr(sys, "frozen", False):
        valid_origin = len(sys.argv) >= 2 and sys.argv[1] == EXTENSION_ORIGIN
    else:
        # The source-only developer launcher passes the expected origin first.
        valid_origin = len(sys.argv) >= 3 and sys.argv[1] == sys.argv[2]
    if not valid_origin:
        return 1
    try:
        request = read_request(sys.stdin.buffer)
        if valid_request(request):
            from vaultsafe.browser_ipc import request_desktop
            response = request_desktop(request)
        else:
            response = {"code": "invalid"}
    except (ValueError, RecursionError):
        response = {"code": "invalid"}
    except Exception:
        response = {"code": "host_error"}
    payload = encode_message(response)
    sys.stdout.buffer.write(LENGTH.pack(len(payload)) + payload)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
