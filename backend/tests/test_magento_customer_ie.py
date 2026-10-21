import os, sys
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

load_dotenv('backend/.env')
sys.path.append('backend')

from app.core.service.magento_service import MagentoService
from app.core.db import models

def test_extract_magento_ie_from_custom_attributes():
    mock_db = MagicMock()
    mock_config = MagicMock()
    mock_config.base_url = "https://example.com"
    mock_config.store_view_code = "default"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_config

    service = MagentoService(mock_db, id_empresa=3)

    # Caso com custom_attributes no billing_address
    order_data = {
        "increment_id": "000001870",
        "billing_address": {
            "custom_attributes": [
                {"attribute_code": "ie", "value": "90.814.179-27"}
            ]
        }
    }
    ie = service._extract_magento_ie(order_data, order_data["billing_address"])
    assert ie == "9081417927"

def test_find_or_create_customer_pj_sefaz_lookup():
    mock_db = MagicMock()
    mock_config = MagicMock()
    mock_config.base_url = "https://example.com"
    mock_config.store_view_code = "default"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_config

    service = MagentoService(mock_db, id_empresa=3)

    # Durante _find_or_create_customer: busca por CNPJ -> None, busca por email -> None
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None,        # busca por CNPJ -> None
        None         # busca por email -> None
    ]

    order_data = {
        "increment_id": "000001870",
        "customer_email": "hzibetti@gmail.com",
        "billing_address": {
            "firstname": "Tolehidro Mangueiras e Hidráulicos LTDA",
            "lastname": "Tolehidro",
            "vat_id": "33.615.973/0001-94",
            "email": "hzibetti@gmail.com",
            "telephone": "45999333638",
            "postcode": "85901010",
            "region_code": "PR",
            "city": "Toledo",
            "street": ["Rua Piratini", "1597", "Casa", "Centro"]
        }
    }

    # Mock da SEFAZ
    mock_sefaz_resp = {
        "ie": "9081417927",
        "habilitado": True,
        "cSit": "1",
        "razao_social": "TOLEHIDRO MANGUEIRAS E HIDRAULICOS LTDA",
        "nome_fantasia": "TOLEHIDRO MANGUEIRAS E HIDRAULICOS",
        "cidade_ibge": "4127700"
    }

    with patch('app.core.service.nfe_service.NFeService') as mock_nfe_cls:
        mock_nfe_instance = MagicMock()
        mock_nfe_instance.consultar_cadastro_sefaz.return_value = mock_sefaz_resp
        mock_nfe_cls.return_value = mock_nfe_instance

        cliente = service._find_or_create_customer(order_data)

        # Verifica se o cliente foi instanciado com os dados enriquecidos
        mock_db.add.assert_called_once()
        created_client = mock_db.add.call_args[0][0]
        assert created_client.cpf_cnpj == "33615973000194"
        assert created_client.inscricao_estadual == "9081417927"
        assert created_client.indicador_ie == models.CadastroIndicadorIEEnum.contribuinte_icms
        assert created_client.fantasia == "TOLEHIDRO MANGUEIRAS E HIDRAULICOS"
        assert created_client.cidade_ibge == "4127700"

def test_find_or_create_customer_updates_existing_client():
    mock_db = MagicMock()
    mock_config = MagicMock()
    mock_config.base_url = "https://example.com"
    mock_config.store_view_code = "default"
    
    # Cliente existente no banco da empresa 3, mas sem IE e como não contribuinte
    existing_client = models.Cadastro(
        id=5656,
        id_empresa=3,
        cpf_cnpj="33615973000194",
        nome_razao="TOLEHIDRO MANGUEIRAS",
        tipo_pessoa=models.CadastroTipoPessoaEnum.juridica,
        indicador_ie=models.CadastroIndicadorIEEnum.nao_contribuinte,
        inscricao_estadual=None
    )

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_config,    # config
        existing_client # busca por CNPJ -> existing_client
    ]

    service = MagentoService(mock_db, id_empresa=3)

    order_data = {
        "increment_id": "000001870",
        "billing_address": {
            "vat_id": "33.615.973/0001-94",
            "region_code": "PR",
            "street": ["Rua Piratini", "1597"]
        }
    }

    mock_sefaz_resp = {
        "ie": "9081417927",
        "habilitado": True,
        "cSit": "1",
        "razao_social": "TOLEHIDRO MANGUEIRAS E HIDRAULICOS LTDA",
        "nome_fantasia": "TOLEHIDRO MANGUEIRAS E HIDRAULICOS",
        "cidade_ibge": "4127700"
    }

    with patch('app.core.service.nfe_service.NFeService') as mock_nfe_cls:
        mock_nfe_instance = MagicMock()
        mock_nfe_instance.consultar_cadastro_sefaz.return_value = mock_sefaz_resp
        mock_nfe_cls.return_value = mock_nfe_instance

        res = service._find_or_create_customer(order_data)

        assert res.inscricao_estadual == "9081417927"
        assert res.indicador_ie == models.CadastroIndicadorIEEnum.contribuinte_icms
        assert res.fantasia == "TOLEHIDRO MANGUEIRAS E HIDRAULICOS"
        mock_db.commit.assert_called()

if __name__ == "__main__":
    print("Running test_extract_magento_ie_from_custom_attributes...")
    test_extract_magento_ie_from_custom_attributes()
    print("Running test_find_or_create_customer_pj_sefaz_lookup...")
    test_find_or_create_customer_pj_sefaz_lookup()
    print("Running test_find_or_create_customer_updates_existing_client...")
    test_find_or_create_customer_updates_existing_client()
    print("ALL TESTS PASSED!")
