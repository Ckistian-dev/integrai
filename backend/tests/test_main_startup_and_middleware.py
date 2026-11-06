import unittest
from unittest.mock import patch, MagicMock
import httpx
from app.core.error_codes import SystemErrorCode

class TestMainLoggingStartup(unittest.IsolatedAsyncioTestCase):
    @patch("app.main.sync_database_schema")
    @patch("app.main.start_backup_scheduler")
    @patch("app.main.start_log_scheduler")
    def test_startup_initializes_log_scheduler(self, mock_start_log, mock_backup, mock_sync):
        from app.main import on_startup
        on_startup()
        mock_start_log.assert_called_once()
        mock_backup.assert_called_once()

    @patch("app.main.log_error")
    async def test_unhandled_exception_logged_with_system_error_code(self, mock_log_err):
        from app.main import app
        from fastapi import APIRouter
        
        # Cria uma rota de teste que levanta exceção inesperada
        test_router = APIRouter()
        @test_router.get("/test-unhandled-exception-endpoint")
        def route_with_bug():
            raise RuntimeError("Falha inesperada no servidor")
            
        app.include_router(test_router)
        
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver"
        ) as client:
            response = await client.get("/test-unhandled-exception-endpoint")
            self.assertEqual(response.status_code, 500)
            mock_log_err.assert_called()
            call_args = mock_log_err.call_args[0]
            self.assertIn(SystemErrorCode.UNHANDLED_EXCEPTION, call_args)

if __name__ == "__main__":
    unittest.main()
