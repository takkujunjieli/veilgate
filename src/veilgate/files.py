"""POSIX descriptor-relative reads; no check-then-open path resolution."""

import os
import stat

from veilgate.errors import GatewayError, StartupError


class FileStore:
    def __init__(self, root: str, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self._root_fd = -1
        fd = -1
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            fd = os.open("/", flags)
            for part in root.split("/"):
                if not part:
                    continue
                next_fd = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            self._root_fd = fd
        except (OSError, AttributeError):
            if fd >= 0:
                os.close(fd)
            raise StartupError("invalid_data_root") from None

    def close(self) -> None:
        if self._root_fd >= 0:
            os.close(self._root_fd)
            self._root_fd = -1

    def read(self, relative_path: str) -> bytes:
        # Defense in depth: never rely solely on configuration validation.
        parts = relative_path.split("/")
        if any(part in ("", ".", "..") for part in parts) or "\\" in relative_path:
            raise GatewayError("source_unavailable", 422)
        directory_fd = file_fd = -1
        try:
            directory_fd = os.dup(self._root_fd)
            for part in parts[:-1]:
                next_fd = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=directory_fd,
                )
                os.close(directory_fd)
                directory_fd = next_fd
            file_fd = os.open(
                parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=directory_fd,
            )
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise GatewayError("source_unavailable", 422)
            if before.st_size > self.max_bytes:
                raise GatewayError("source_limit_exceeded", 413)
            chunks = bytearray()
            while len(chunks) <= self.max_bytes:
                chunk = os.read(file_fd, min(65_536, self.max_bytes + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            if len(chunks) > self.max_bytes:
                raise GatewayError("source_limit_exceeded", 413)
            after = os.fstat(file_fd)
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise GatewayError("source_changed", 409)
            return bytes(chunks)
        except (OSError, ValueError):
            raise GatewayError("source_unavailable", 422) from None
        finally:
            if file_fd >= 0:
                os.close(file_fd)
            if directory_fd >= 0:
                os.close(directory_fd)
