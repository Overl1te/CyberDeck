import importlib
import unittest


_NEW_LAYOUT_MODULES = (
    "cyberdeck.api",
    "cyberdeck.api.core",
    "cyberdeck.api.local",
    "cyberdeck.api.system",
    "cyberdeck.input",
    "cyberdeck.input.backend",
    "cyberdeck.input.backends.base",
    "cyberdeck.input.backends.linux",
    "cyberdeck.input.backends.windows",
    "cyberdeck.launcher",
    "cyberdeck.launcher.app",
    "cyberdeck.launcher.shared",
    "cyberdeck.launcher.ui.home",
    "cyberdeck.platform.wayland_setup",
    "cyberdeck.video",
    "cyberdeck.video.api",
    "cyberdeck.video.core",
    "cyberdeck.video.ffmpeg",
    "cyberdeck.video.mjpeg",
    "cyberdeck.video.streamer",
    "cyberdeck.video.wayland",
    "cyberdeck.ws",
    "cyberdeck.ws.mouse",
    "cyberdeck.ws.protocol",
)


class PackageLayoutImportsBehaviorTests(unittest.TestCase):
    def test_new_package_layout_imports_cleanly(self):
        """Validate scenario: package modules must import with the new folder layout."""
        for module_name in _NEW_LAYOUT_MODULES:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)


if __name__ == "__main__":
    unittest.main()
