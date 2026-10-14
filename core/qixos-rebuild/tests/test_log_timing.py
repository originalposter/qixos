"""Every log line says how long ago the previous one was.

A switch runs for minutes between two lines, and the gap is the only record of where the
time went.
"""
import logging

from qixos_rebuild.qrexec import protocol


def test_a_record_carries_the_time_since_the_one_before(monkeypatch):
    clock = iter([100.0, 100.0, 163.4])
    monkeypatch.setattr(protocol.time, "monotonic", lambda: next(clock))
    since_last = protocol.SinceLast()

    gaps = []
    for _ in range(2):
        record = logging.makeLogRecord({})
        since_last.filter(record)
        gaps.append(record.since_last)

    assert gaps == ["+0s", "+63s"]
