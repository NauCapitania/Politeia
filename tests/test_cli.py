import json
import sys

import pytest

from engine import cli


def test_failed_replay_prints_result_and_exits_nonzero(monkeypatch, capsys):
    result = {"run_id": "replay-run", "status": "failed", "error": "validation errors"}
    monkeypatch.setattr(sys, "argv", ["politeia", "replay-proposals", "--proposal-id", "123"])
    monkeypatch.setattr(cli, "session_factory", object)
    monkeypatch.setattr(cli, "replay_proposals", lambda *args, **kwargs: result)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out) == result
