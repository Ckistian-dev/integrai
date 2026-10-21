import os, sys
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

load_dotenv('backend/.env')
sys.path.append('backend')

from app.core.service.nfe_service import NFeService
from app.core.db import models

XML_SEFAZ_SUCESSO = b"""<env:Envelope xmlns:env='http://www.w3.org/2003/05/soap-envelope'>
<env:Body>
  <retConsCad versao='2.00' xmlns='http://www.portalfiscal.inf.br/nfe'>
    <infCons>
      <cStat>111</cStat>
      <xMotivo>Consulta cadastro com uma ocorrencia</xMotivo>
      <UF>PR</UF>
      <CNPJ>33615973000194</CNPJ>
      <infCad>
        <IE>9081417927</IE>
        <CNPJ>33615973000194</CNPJ>
        <UF>PR</UF>
        <cSit>1</cSit>
        <indCredNFe>4</indCredNFe>
        <xNome>TOLEHIDRO MANGUEIRAS E HIDRAULICOS LTDA</xNome>
        <xFant>TOLEHIDRO MANGUEIRAS E HIDRAULICOS</xFant>
        <ender>
          <cMun>4127700</cMun>
          <xMun>TOLEDO</xMun>
          <CEP>85904460</CEP>
        </ender>
      </infCad>
    </infCons>
  </retConsCad>
</env:Body>
</env:Envelope>"""

XML_SEFAZ_NAO_ENCONTRADO = b"""<env:Envelope xmlns:env='http://www.w3.org/2003/05/soap-envelope'>
<env:Body>
  <retConsCad versao='2.00' xmlns='http://www.portalfiscal.inf.br/nfe'>
    <infCons>
      <cStat>259</cStat>
      <xMotivo>Rejeicao: CNPJ da consulta nao cadastrado como contribuinte na UF</xMotivo>
      <UF>SP</UF>
      <CNPJ>00000000000000</CNPJ>
    </infCons>
  </retConsCad>
</env:Body>
</env:Envelope>"""

def test_consultar_cadastro_sefaz_sucesso():
    mock_db = MagicMock()
    mock_empresa = MagicMock()
    mock_empresa.certificado_arquivo = b"fakecert"
    mock_empresa.certificado_senha = "123"
    mock_empresa.estado.value = "PR"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_empresa

    service = NFeService(mock_db, id_empresa=1)
    
    with patch.object(service, '_get_certificado_path', return_value='/tmp/fake.pfx'), \
         patch('os.path.exists', return_value=True), \
         patch('os.remove', return_value=None), \
         patch('app.core.service.nfe_service.ComunicacaoSefaz') as mock_comunicacao_cls:
        
        mock_con = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = XML_SEFAZ_SUCESSO
        mock_con.consulta_cadastro.return_value = mock_resp
        mock_comunicacao_cls.return_value = mock_con

        resultado = service.consultar_cadastro_sefaz("33.615.973/0001-94", "PR")
        
        assert resultado is not None
        assert resultado["ie"] == "9081417927"
        assert resultado["habilitado"] is True
        assert resultado["cSit"] == "1"
        assert resultado["razao_social"] == "TOLEHIDRO MANGUEIRAS E HIDRAULICOS LTDA"
        assert resultado["nome_fantasia"] == "TOLEHIDRO MANGUEIRAS E HIDRAULICOS"
        assert resultado["cidade_ibge"] == "4127700"

def test_consultar_cadastro_sefaz_nao_cadastrado():
    mock_db = MagicMock()
    mock_empresa = MagicMock()
    mock_empresa.certificado_arquivo = b"fakecert"
    mock_empresa.certificado_senha = "123"
    mock_empresa.estado.value = "PR"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_empresa

    service = NFeService(mock_db, id_empresa=1)
    
    with patch.object(service, '_get_certificado_path', return_value='/tmp/fake.pfx'), \
         patch('os.path.exists', return_value=True), \
         patch('os.remove', return_value=None), \
         patch('app.core.service.nfe_service.ComunicacaoSefaz') as mock_comunicacao_cls:
        
        mock_con = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = XML_SEFAZ_NAO_ENCONTRADO
        mock_con.consulta_cadastro.return_value = mock_resp
        mock_comunicacao_cls.return_value = mock_con

        resultado = service.consultar_cadastro_sefaz("00.000.000/0000-00", "SP")
        assert resultado is None

def test_consultar_cadastro_sefaz_sem_certificado():
    mock_db = MagicMock()
    mock_empresa = MagicMock()
    mock_empresa.certificado_arquivo = None
    mock_empresa.certificado_senha = None
    mock_db.query.return_value.filter.return_value.first.return_value = mock_empresa

    try:
        service = NFeService(mock_db, id_empresa=1)
        resultado = service.consultar_cadastro_sefaz("33615973000194", "PR")
        assert resultado is None
    except Exception as e:
        # NFeService valida presença do certificado no __init__
        assert "Certificado digital ou senha" in str(e)

if __name__ == "__main__":
    print("Running test_consultar_cadastro_sefaz_sucesso...")
    test_consultar_cadastro_sefaz_sucesso()
    print("Running test_consultar_cadastro_sefaz_nao_cadastrado...")
    test_consultar_cadastro_sefaz_nao_cadastrado()
    print("Running test_consultar_cadastro_sefaz_sem_certificado...")
    test_consultar_cadastro_sefaz_sem_certificado()
    print("ALL TESTS PASSED!")
