import unittest
from app.core.error_codes import (
    AuthErrorCode, NfeErrorCode, DfeErrorCode, ShopeeErrorCode,
    MeliErrorCode, MagentoErrorCode, IntelipostErrorCode,
    GenericErrorCode, DbErrorCode, SystemErrorCode, LogStatus
)

class TestErrorCodes(unittest.TestCase):
    def test_error_code_prefixes(self):
        self.assertTrue(AuthErrorCode.INVALID_CREDENTIALS.startswith("ERR_AUTH_"))
        self.assertTrue(AuthErrorCode.USER_NOT_FOUND.startswith("ERR_AUTH_"))
        self.assertTrue(NfeErrorCode.SEFAZ_REJECTION.startswith("ERR_NFE_"))
        self.assertTrue(NfeErrorCode.SCHEMA_VALIDATION.startswith("ERR_NFE_"))
        self.assertTrue(DfeErrorCode.DIST_NSU_FAILED.startswith("ERR_DFE_"))
        self.assertTrue(ShopeeErrorCode.TOKEN_EXPIRED.startswith("ERR_SHOPEE_"))
        self.assertTrue(MeliErrorCode.ORDER_FETCH_FAILED.startswith("ERR_MELI_"))
        self.assertTrue(MagentoErrorCode.API_ERROR.startswith("ERR_MAGENTO_"))
        self.assertTrue(IntelipostErrorCode.QUOTE_FAILED.startswith("ERR_INTELIPOST_"))
        self.assertTrue(GenericErrorCode.RECORD_NOT_FOUND.startswith("ERR_GENERIC_"))
        self.assertTrue(DbErrorCode.INTEGRITY_VIOLATION.startswith("ERR_DB_"))
        self.assertTrue(SystemErrorCode.UNHANDLED_EXCEPTION.startswith("ERR_SYSTEM_"))
        self.assertTrue(LogStatus.SUCCESS.startswith("STATUS_"))

if __name__ == "__main__":
    unittest.main()
