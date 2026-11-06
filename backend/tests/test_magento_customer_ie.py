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

def test_extract_magento_ie_from_customer_payload():
    mock_db = MagicMock()
    mock_config = MagicMock()
    mock_config.base_url = "https://example.com"
    mock_config.store_view_code = "default"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_config

    service = MagentoService(mock_db, id_empresa=3)

    # Payload exato fornecido pelo usuário
    customer_payload = {
        "id": 920,
        "group_id": 2,
        "default_billing": "964",
        "default_shipping": "963",
        "created_at": "2026-10-21 20:28:54",
        "updated_at": "2026-10-21 20:30:46",
        "created_in": "Visão principal",
        "email": "lucas@mageshop.com.br",
        "firstname": "Lucas PJ",
        "lastname": "mageshop",
        "store_id": 1,
        "taxvat": "61.027.898/0001-86",
        "website_id": 1,
        "addresses": [
            {
                "id": 963,
                "customer_id": 920,
                "region": {"region_code": "PR", "region": "Paraná", "region_id": 499},
                "region_id": 499,
                "country_id": "BR",
                "street": ["Rua Amir Dalla Vecchia", "503", "", "Vila Gaúcha"],
                "telephone": "(45)99951-5687",
                "postcode": "85966218",
                "city": "Marechal Cândido Rondon",
                "firstname": "Lucas PJ",
                "lastname": "mageshop",
                "vat_id": "61.027.898/0001-86",
                "default_shipping": True
            },
            {
                "id": 964,
                "customer_id": 920,
                "region": {"region_code": "PR", "region": "Paraná", "region_id": 499},
                "region_id": 499,
                "country_id": "BR",
                "street": ["Rua Amir Dalla Vecchia", "503", "", "Vila Gaúcha"],
                "telephone": "45999515687",
                "postcode": "85966218",
                "city": "Marechal Cândido Rondon",
                "firstname": "Lucas PJ",
                "lastname": "mageshop",
                "vat_id": "61.027.898/0001-86",
                "default_billing": True
            }
        ],
        "disable_auto_group_change": 0,
        "extension_attributes": {
            "is_subscribed": False
        },
        "custom_attributes": [
            {"attribute_code": "is_disabled", "value": "0"},
            {"attribute_code": "is_approved", "value": "0"},
            {"attribute_code": "ww_is_disabled", "value": False},
            {"attribute_code": "ie", "value": "ISENTO"},
            {"attribute_code": "cnpj", "value": "61.027.898/0001-86"},
            {"attribute_code": "customer_id_pagarme", "value": "0"}
        ]
    }

    # 1. Testando chamada passando customer_data explicitamente
    ie1 = service._extract_magento_ie(order_data={}, billing={}, customer_data=customer_payload)
    assert ie1 == "ISENTO"

    # 2. Testando chamada passando diretamente o payload de cliente como primeiro argumento
    ie2 = service._extract_magento_ie(customer_payload)
    assert ie2 == "ISENTO"

def test_find_or_create_customer_with_customer_api_lookup():
    mock_db = MagicMock()
    mock_config = MagicMock()
    mock_config.base_url = "https://example.com"
    mock_config.store_view_code = "default"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_config

    service = MagentoService(mock_db, id_empresa=3)

    # Simula cliente ainda não existente no ERP
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None, # busca por CNPJ
        None  # busca por email
    ]

    order_data = {
        "increment_id": "000001880",
        "customer_id": 920,
        "customer_email": "lucas@mageshop.com.br",
        "billing_address": {
            "firstname": "Lucas PJ",
            "lastname": "mageshop",
            "vat_id": "61.027.898/0001-86",
            "email": "lucas@mageshop.com.br",
            "telephone": "45999515687",
            "postcode": "85966218",
            "region_code": "PR",
            "city": "Marechal Cândido Rondon",
            "street": ["Rua Amir Dalla Vecchia", "503", "", "Vila Gaúcha"]
        }
    }

    customer_payload = {
        "id": 920,
        "email": "lucas@mageshop.com.br",
        "taxvat": "61.027.898/0001-86",
        "custom_attributes": [
            {"attribute_code": "ie", "value": "ISENTO"},
            {"attribute_code": "cnpj", "value": "61.027.898/0001-86"}
        ]
    }

    with patch.object(service, 'get_customer', return_value=customer_payload) as mock_get_cust:
        with patch('app.core.service.nfe_service.NFeService') as mock_nfe_cls:
            cliente = service._find_or_create_customer(order_data)

            mock_get_cust.assert_called_once_with(920)
            # Não deve chamar SEFAZ já que o cliente tem IE = ISENTO informada
            mock_nfe_cls.assert_not_called()

            mock_db.add.assert_called_once()
            created_client = mock_db.add.call_args[0][0]
            assert created_client.cpf_cnpj == "61027898000186"
            assert created_client.inscricao_estadual == "ISENTO"
            assert created_client.indicador_ie == models.CadastroIndicadorIEEnum.isento

def test_find_or_create_customer_updates_existing_client_to_isento():
    mock_db = MagicMock()
    mock_config = MagicMock()
    mock_config.base_url = "https://example.com"
    mock_config.store_view_code = "default"

    # Cliente já cadastrado no banco, mas com indicador_ie='9' (não contribuinte) e sem IE
    existing_client = models.Cadastro(
        id=777,
        id_empresa=3,
        cpf_cnpj="61027898000186",
        nome_razao="LUCAS PJ",
        tipo_pessoa=models.CadastroTipoPessoaEnum.juridica,
        indicador_ie=models.CadastroIndicadorIEEnum.nao_contribuinte,
        inscricao_estadual=None
    )

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_config,
        existing_client
    ]

    service = MagentoService(mock_db, id_empresa=3)

    order_data = {
        "increment_id": "000001881",
        "customer_id": 920,
        "billing_address": {
            "vat_id": "61.027.898/0001-86",
            "region_code": "PR"
        }
    }

    customer_payload = {
        "id": 920,
        "taxvat": "61.027.898/0001-86",
        "custom_attributes": [
            {"attribute_code": "ie", "value": "ISENTO"}
        ]
    }

    with patch.object(service, 'get_customer', return_value=customer_payload):
        res = service._find_or_create_customer(order_data)
        assert res.inscricao_estadual == "ISENTO"
        assert res.indicador_ie == models.CadastroIndicadorIEEnum.isento
        mock_db.commit.assert_called()

if __name__ == "__main__":
    print("Running test_extract_magento_ie_from_custom_attributes...")
    test_extract_magento_ie_from_custom_attributes()
    print("Running test_find_or_create_customer_pj_sefaz_lookup...")
    test_find_or_create_customer_pj_sefaz_lookup()
    print("Running test_find_or_create_customer_updates_existing_client...")
    test_find_or_create_customer_updates_existing_client()
    print("Running test_extract_magento_ie_from_customer_payload...")
    test_extract_magento_ie_from_customer_payload()
    print("Running test_find_or_create_customer_with_customer_api_lookup...")
    test_find_or_create_customer_with_customer_api_lookup()
    print("Running test_find_or_create_customer_updates_existing_client_to_isento...")
    test_find_or_create_customer_updates_existing_client_to_isento()
    print("ALL TESTS PASSED!")


