import unittest
from unittest.mock import patch, MagicMock
from app.crud.crud_user import authenticate_user
from app.api.v1.endpoints.auth import login_for_access_token

class TestAuthDashboardLogs(unittest.TestCase):
    @patch("app.crud.crud_user.log_warning")
    @patch("app.crud.crud_user.log_info")
    def test_authenticate_user_logs_user_not_found(self, mock_info, mock_warn):
        db = MagicMock()
        db.query().filter().order_by().first.return_value = None
        user = authenticate_user(db, "inexistente@var.com", "senha123")
        self.assertIsNone(user)
        mock_warn.assert_called()
        # Verifica se o código de erro passado é ERR_AUTH_USER_NOT_FOUND
        args, kwargs = mock_warn.call_args
        self.assertEqual(args[0], "AUTH")
        self.assertEqual(args[3], "ERR_AUTH_USER_NOT_FOUND")

    @patch("app.crud.crud_user.log_warning")
    @patch("app.crud.crud_user.log_info")
    def test_authenticate_user_logs_invalid_password(self, mock_info, mock_warn):
        db = MagicMock()
        fake_user = MagicMock()
        fake_user.id = 99
        fake_user.id_empresa = 1
        fake_user.senha = "senha_correta"
        db.query().filter().order_by().first.return_value = fake_user

        user = authenticate_user(db, "user@var.com", "senha_errada")
        self.assertIsNone(user)
        mock_warn.assert_called()
        args, kwargs = mock_warn.call_args
        self.assertEqual(args[0], "AUTH")
        self.assertEqual(args[3], "ERR_AUTH_INVALID_CREDENTIALS")

if __name__ == "__main__":
    unittest.main()
