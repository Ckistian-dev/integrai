import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
from datetime import datetime, timedelta
import pytz
from app.core.service.log_service import rotate_and_sync_logs
from app.core.logger import close_logging

class TestLogService(unittest.TestCase):
    def tearDown(self):
        close_logging()

    def test_rotate_and_sync_logs_uploads_and_cleans_local(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sp_tz = pytz.timezone("America/Sao_Paulo")
            yesterday = datetime.now(sp_tz) - timedelta(days=1)
            yesterday_file = os.path.join(temp_dir, f"integrai_logs_{yesterday.strftime('%Y-%m-%d')}.txt")
            with open(yesterday_file, "w", encoding="utf-8") as f:
                f.write("Log do dia anterior\n")

            mock_drive = MagicMock()
            mock_drive.upload_file.return_value = "drive_file_123"
            mock_drive.delete_old_files_by_prefix.return_value = 1

            result = rotate_and_sync_logs(logs_dir=temp_dir, drive_service=mock_drive)

            self.assertTrue(result["success"])
            self.assertEqual(result["uploaded_files"], 1)
            self.assertFalse(os.path.exists(yesterday_file), "Arquivo do dia anterior deve ser deletado localmente")
            mock_drive.upload_file.assert_called_once()
            mock_drive.delete_old_files_by_prefix.assert_called_once()
            close_logging()

    def test_rotate_does_not_delete_if_upload_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sp_tz = pytz.timezone("America/Sao_Paulo")
            yesterday = datetime.now(sp_tz) - timedelta(days=1)
            yesterday_file = os.path.join(temp_dir, f"integrai_logs_{yesterday.strftime('%Y-%m-%d')}.txt")
            with open(yesterday_file, "w", encoding="utf-8") as f:
                f.write("Log preservado caso falhe upload\n")

            mock_drive = MagicMock()
            mock_drive.upload_file.side_effect = Exception("Erro de conexão com o Drive")

            result = rotate_and_sync_logs(logs_dir=temp_dir, drive_service=mock_drive)

            self.assertFalse(result["success"])
            self.assertTrue(os.path.exists(yesterday_file), "Arquivo deve ser mantido localmente se o upload falhar")
            close_logging()

if __name__ == "__main__":
    unittest.main()
