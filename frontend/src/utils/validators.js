// frontend/src/utils/validators.js

/**
 * Valida um número de CPF segundo o algoritmo canônico dos dígitos verificadores (módulo 11).
 * @param {string} cpf 
 * @returns {boolean}
 */
export const isValidCpf = (cpf) => {
  if (!cpf) return false;

  const clean = String(cpf).replace(/\D/g, '');
  if (clean.length !== 11) return false;

  // Rejeita CPFs com todos os dígitos iguais (ex: 000.000.000-00, 111.111.111-11, etc.)
  if (/^(\d)\1{10}$/.test(clean)) return false;

  // Validação do 1º dígito verificador
  let sum = 0;
  for (let i = 0; i < 9; i++) {
    sum += parseInt(clean.charAt(i), 10) * (10 - i);
  }
  let remainder = (sum * 10) % 11;
  if (remainder === 10 || remainder === 11) remainder = 0;
  if (remainder !== parseInt(clean.charAt(9), 10)) return false;

  // Validação do 2º dígito verificador
  sum = 0;
  for (let i = 0; i < 10; i++) {
    sum += parseInt(clean.charAt(i), 10) * (11 - i);
  }
  remainder = (sum * 10) % 11;
  if (remainder === 10 || remainder === 11) remainder = 0;
  if (remainder !== parseInt(clean.charAt(10), 10)) return false;

  return true;
};

/**
 * Valida um número de CNPJ (suporta formato numérico e alfanumérico IN RFB 2.229/2025).
 * @param {string} cnpj 
 * @returns {boolean}
 */
export const isValidCnpj = (cnpj) => {
  if (!cnpj) return false;

  const clean = String(cnpj).replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
  if (clean.length !== 14) return false;

  // Rejeita se todos os caracteres forem iguais
  if (/^(.)\1{13}$/.test(clean)) return false;

  const pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];

  try {
    // 1º dígito verificador
    let sum1 = 0;
    for (let i = 0; i < 12; i++) {
      sum1 += (clean.charCodeAt(i) - 48) * pesos1[i];
    }
    let rest1 = sum1 % 11;
    let dv1 = rest1 < 2 ? 0 : 11 - rest1;
    if (dv1 !== parseInt(clean.charAt(12), 10)) return false;

    // 2º dígito verificador
    let sum2 = 0;
    for (let i = 0; i < 13; i++) {
      sum2 += (clean.charCodeAt(i) - 48) * pesos2[i];
    }
    let rest2 = sum2 % 11;
    let dv2 = rest2 < 2 ? 0 : 11 - rest2;
    if (dv2 !== parseInt(clean.charAt(13), 10)) return false;

    return true;
  } catch {
    return false;
  }
};

/**
 * Validação genérica para CPF ou CNPJ baseada no tamanho do documento limpo.
 * @param {string} doc 
 * @returns {boolean}
 */
export const isValidCpfCnpj = (doc) => {
  if (!doc) return false;
  const clean = String(doc).replace(/[^a-zA-Z0-9]/g, '');
  if (clean.length === 11 && /^\d{11}$/.test(clean)) {
    return isValidCpf(clean);
  }
  if (clean.length === 14) {
    return isValidCnpj(clean);
  }
  return false;
};
