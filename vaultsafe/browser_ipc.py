"""Windows named pipe for one Chrome request at a time within this logon session."""

from contextlib import closing
from threading import Event, Thread
from time import monotonic

import ntsecuritycon
import pywintypes
import win32api
import win32con
import win32event
import win32file
import win32pipe
import win32security
import winerror

from .browser_protocol import MAX_MESSAGE, decode_message, encode_message


IO_TIMEOUT = 2.0
RESPONSE_TIMEOUT = 6.0
LOGON_GROUP = 0xC0000000  # SE_GROUP_LOGON_ID
FIRST_PIPE_INSTANCE = 0x00080000
SECURITY_IDENTIFICATION = 0x00010000
CLIENT_ACCESS = (ntsecuritycon.FILE_READ_DATA | ntsecuritycon.FILE_WRITE_DATA
                 | ntsecuritycon.FILE_WRITE_ATTRIBUTES | ntsecuritycon.SYNCHRONIZE)


def _logon_sid(process):
    with closing(win32security.OpenProcessToken(process, win32con.TOKEN_QUERY)) as token:
        groups = win32security.GetTokenInformation(token, win32security.TokenGroups)
    for sid, attributes in groups:
        if attributes & LOGON_GROUP == LOGON_GROUP:
            return sid
    raise RuntimeError("Windows token has no logon SID")


def _pipe_identity():
    sid = _logon_sid(win32api.GetCurrentProcess())
    return rf"\\.\pipe\VaultSafe.Chrome.{win32security.ConvertSidToStringSid(sid)}", sid


def _pipe_security(sid):
    acl = win32security.ACL()
    acl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.GENERIC_ALL, sid)
    descriptor = win32security.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorDacl(True, acl, False)
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR = descriptor
    return attributes


def _io(handle, begin, timeout, stop=None):
    """Finish or cancel the overlapped operation before releasing its buffer."""
    with closing(win32event.CreateEvent(None, True, False, None)) as event:
        overlapped = pywintypes.OVERLAPPED()
        overlapped.hEvent = event
        status, buffer = begin(overlapped)
        if status == winerror.ERROR_PIPE_CONNECTED:
            return None
        if status == winerror.ERROR_MORE_DATA:
            raise ValueError("Message too large")
        if status not in (0, winerror.ERROR_IO_PENDING):
            raise OSError("Unexpected pipe result")
        deadline = monotonic() + timeout if timeout is not None else None
        while status == winerror.ERROR_IO_PENDING:
            if win32event.WaitForSingleObject(event, 75) == win32event.WAIT_OBJECT_0:
                break
            if (stop is not None and stop.is_set()) or (deadline and monotonic() >= deadline):
                try:
                    win32file.CancelIo(handle)
                except pywintypes.error as error:
                    if error.winerror != winerror.ERROR_NOT_FOUND:
                        raise
                try:
                    win32file.GetOverlappedResult(handle, overlapped, True)
                except pywintypes.error:
                    pass
                raise TimeoutError
        count = win32file.GetOverlappedResult(handle, overlapped, False)
        return bytes(buffer[:count]) if buffer is not None else None


def _read(handle, timeout, stop=None):
    return _io(handle, lambda completion: win32file.ReadFile(handle, MAX_MESSAGE + 1, completion),
               timeout, stop)


def _write(handle, message):
    data = encode_message(message)

    def begin(completion):
        status, _ = win32file.WriteFile(handle, data, completion)
        return status, None

    _io(handle, begin, IO_TIMEOUT)


class PipeServer:
    def __init__(self, dispatch):
        self._stop = Event()
        try:
            path, sid = _pipe_identity()
            self._handle = win32pipe.CreateNamedPipe(
                path, win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED
                | FIRST_PIPE_INSTANCE,
                win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE
                | win32pipe.PIPE_REJECT_REMOTE_CLIENTS,
                1, MAX_MESSAGE, MAX_MESSAGE, 250, _pipe_security(sid),
            )
        except pywintypes.error as error:
            raise OSError("Could not start the VaultSafe named pipe") from error
        self._dispatch = dispatch
        self._worker = Thread(target=self._serve, daemon=True, name="vaultsafe-chrome-pipe")
        self._worker.start()

    def _connect(self, completion):
        try:
            status = win32pipe.ConnectNamedPipe(self._handle, completion)
        except pywintypes.error as error:
            if error.winerror != winerror.ERROR_PIPE_CONNECTED:
                raise
            status = winerror.ERROR_PIPE_CONNECTED
        return status, None

    def _serve(self):
        with closing(self._handle) as handle:
            while not self._stop.is_set():
                try:
                    _io(handle, self._connect, None, self._stop)
                    data = _read(handle, IO_TIMEOUT, self._stop)
                    try:
                        request = decode_message(data)
                    except (ValueError, RecursionError):
                        response = {"code": "invalid"}
                    else:
                        response = self._dispatch(request)
                    if not self._stop.is_set():
                        _write(handle, response)
                        # Disconnect discards unread bytes, so wait for the client to close.
                        _read(handle, IO_TIMEOUT, self._stop)
                except (OSError, pywintypes.error, ValueError):
                    pass
                finally:
                    try:
                        win32pipe.DisconnectNamedPipe(handle)
                    except pywintypes.error:
                        pass

    def close(self):
        self._stop.set()
        self._worker.join(timeout=0.25)


def request_desktop(request):
    path, sid = _pipe_identity()
    try:
        win32pipe.WaitNamedPipe(path, 1200)
        # Permit a server to identify its client without granting impersonation.
        with closing(win32file.CreateFile(
            path, CLIENT_ACCESS, 0, None, win32con.OPEN_EXISTING,
            win32file.FILE_FLAG_OVERLAPPED | win32con.SECURITY_SQOS_PRESENT
            | SECURITY_IDENTIFICATION, None,
        )) as handle:
            pid = win32pipe.GetNamedPipeServerProcessId(handle)
            with closing(win32api.OpenProcess(
                win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid,
            )) as process:
                if _logon_sid(process) != sid:
                    return {"code": "host_error"}
            win32pipe.SetNamedPipeHandleState(handle, win32pipe.PIPE_READMODE_MESSAGE, None, None)
            _write(handle, request)
            return decode_message(_read(handle, RESPONSE_TIMEOUT))
    except pywintypes.error as error:
        if error.winerror == winerror.ERROR_FILE_NOT_FOUND:
            return {"code": "app_closed"}
        if error.winerror in (winerror.ERROR_PIPE_BUSY, winerror.ERROR_SEM_TIMEOUT):
            return {"code": "busy"}
        return {"code": "host_error"}
    except TimeoutError:
        return {"code": "busy"}
