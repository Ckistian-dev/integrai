import unittest
from unittest.mock import patch, MagicMock

class TestIntegrationsLogging(unittest.TestCase):
    def test_intelipost_has_structured_logging(self):
        from app.api.v1.endpoints import intelipost
        self.assertTrue(hasattr(intelipost, 'log_info'))
        self.assertTrue(hasattr(intelipost, 'log_error'))

    def test_magento_has_structured_logging(self):
        from app.api.v1.endpoints import magento
        self.assertTrue(hasattr(magento, 'log_info'))
        self.assertTrue(hasattr(magento, 'log_error'))

    def test_tiktok_has_structured_logging(self):
        from app.api.v1.endpoints import tiktok
        self.assertTrue(hasattr(tiktok, 'log_info'))
        self.assertTrue(hasattr(tiktok, 'log_error'))

    def test_atendai_has_structured_logging(self):
        from app.api.v1.endpoints import atendai
        self.assertTrue(hasattr(atendai, 'log_info'))
        self.assertTrue(hasattr(atendai, 'log_error'))

if __name__ == "__main__":
    unittest.main()
