import unittest
import os
import tempfile
import logging
from app.core.logger import (
    sanitize_context, format_log_line, log_info, log_error, log_warning,
    init_logging, close_logging, get_current_log_filepath, get_logger
)

class TestLogger(unittest.TestCase):
    def tearDown(self):
        close_logging()

    def test_sanitize_context_removes_secrets(self):
        ctx = {
            "username": "admin",
            "password": "supersecretpassword123",
            "token": "bearer_xyz_token",
            "access_token": "abc_access",
            "secret": "my_secret_key",
            "id": 10,
            "nested": {
                "senha": "outrasenha",
                "normal": "valor_ok"
            }
        }
        clean = sanitize_context(ctx)
        self.assertEqual(clean["password"], "[PROTEGIDO]")
        self.assertEqual(clean["token"], "[PROTEGIDO]")
        self.assertEqual(clean["access_token"], "[PROTEGIDO]")
        self.assertEqual(clean["secret"], "[PROTEGIDO]")
        self.assertEqual(clean["username"], "admin")
        self.assertEqual(clean["id"], 10)
        self.assertEqual(clean["nested"]["senha"], "[PROTEGIDO]")
        self.assertEqual(clean["nested"]["normal"], "valor_ok")

    def test_format_log_line_hierarchy(self):
        line = format_log_line("INFO", "NFE", "nfe_service", "emitir_nfe", "STATUS_SUCCESS", "Nota emitida", {"id": 101})
        self.assertIn("[INFO]", line)
        self.assertIn("[NFE:nfe_service:emitir_nfe]", line)
        self.assertIn("[STATUS_SUCCESS]", line)
        self.assertIn("Nota emitida", line)
        self.assertIn("id: 101", line)

    def test_init_logging_creates_file_and_logs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            init_logging(logs_dir=temp_dir)
            log_filepath = get_current_log_filepath(logs_dir=temp_dir)
            self.assertTrue(os.path.exists(log_filepath))

            log_info("AUTH", "auth_endpoint", "login", "STATUS_SUCCESS", "Usuario logado", {"user_id": 42})
            
            with open(log_filepath, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("[AUTH:auth_endpoint:login]", content)
            self.assertIn("[STATUS_SUCCESS]", content)
            self.assertIn("Usuario logado", content)
            self.assertIn("user_id: 42", content)
            close_logging()

if __name__ == "__main__":
    unittest.main()
