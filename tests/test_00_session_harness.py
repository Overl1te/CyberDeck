import atexit
import glob
import os
import shutil
import tempfile
import unittest

from cyberdeck import config, context


_ORIG_SESSION_FILE = str(config.SESSION_FILE)
_TEST_SESSION_DIR = tempfile.mkdtemp(prefix="cyberdeck-test-sessions-")
config.SESSION_FILE = os.path.join(_TEST_SESSION_DIR, os.path.basename(_ORIG_SESSION_FILE))


def _cleanup_test_sessions() -> None:
    """Clean up test sessions."""
    try:
        context.device_manager.sessions = {}
    except Exception:
        pass

    paths = [config.SESSION_FILE]
    paths.extend(glob.glob(config.SESSION_FILE + ".tmp-*"))
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    try:
        shutil.rmtree(_TEST_SESSION_DIR, ignore_errors=True)
    except Exception:
        pass

    try:
        config.SESSION_FILE = _ORIG_SESSION_FILE
    except Exception:
        pass


atexit.register(_cleanup_test_sessions)


class SessionHarnessTests(unittest.TestCase):
    def test_session_file_is_isolated_for_test_run(self):
        """Validate scenario: test session file is isolated for test run."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        self.assertIn("cyberdeck-test-sessions-", str(config.SESSION_FILE))


if __name__ == "__main__":
    unittest.main()
