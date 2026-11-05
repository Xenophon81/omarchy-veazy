# SPDX-License-Identifier: AGPL-3.0-only
"""Stable machine-readable error codes for the versioned IPC contract."""


class VeazyError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def safe_message(error):
    return "".join(c for c in str(error) if c.isprintable())[:300]
