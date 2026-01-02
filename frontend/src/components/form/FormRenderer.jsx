import React from 'react';
import {
  TextInput,
  BooleanInput,
  SelectInput,
  PasswordInput,
  MaskedInput,
  MASKS,
  AsyncSelectInput,
  DateInput,
  OrderItemsInput
} from '../ui/InputFields';
import { RuleBuilderInput } from '../ui/RuleBuilderInput';
import { CreatableSelectInput } from '../ui/CreatableSelectInput';

/**
 * Este componente atua como um 'switch' para renderizar
 * o componente de input correto com base no tipo de campo
 * fornecido pelos metadados do backend.
 */
const FormRenderer = ({ field, value, onChange, error, modelName }) => {
  // Passa as props comuns para todos os inputs
  const props = {
    field,
    value: value ?? '',
    onChange,
    error,
    modelName, // Passa o modelName para componentes que precisam buscar dados (CreatableSelect)
  };

  const formatMask = field.format_mask;
  const maskProps = (field.type !== 'date' && field.type !== 'datetime' && formatMask)
    ? MASKS[formatMask]
    : null;

  if (maskProps) {
    // Manipulador customizado para máscaras. O IMask retorna o valor limpo (unmaskedValue).
    // 🎯 CORREÇÃO: O IMask passa (value, maskRef). 'value' é o valor COM máscara.
    // Precisamos usar maskRef.unmaskedValue para pegar o valor limpo.
    const handleAccept = (value, maskRef) => {
      let finalValue = maskRef.unmaskedValue;

      // se a propriedade 'mask' da máscara for o tipo Number.
      // 🎯 CORREÇÃO: Verifica também se é nossa máscara 'currency' (que agora usa pattern 'R$ num')
      if ((maskProps.mask === Number || formatMask === 'currency') && finalValue !== '') { 
        // Converte a string limpa (usando '.' como separador decimal interno) para Number
        // Substitui vírgula por ponto caso o unmaskedValue venha com vírgula (devido ao radix)
        finalValue = parseFloat(finalValue.replace(',', '.'));
        if (isNaN(finalValue)) finalValue = null;
      } else if (typeof maskProps === 'string' || Array.isArray(maskProps)) {
        // Se for uma máscara de padrão (como CEP, que é string) ou dinâmica (Array de strings),
        // o valor limpo (unmaskedValue) já é uma string e não precisa de conversão.
        // Mas garantimos que se for vazio, tratamos como null ou string vazia, se for o caso.
        if (finalValue === '') finalValue = null;
      }

      // Simula o evento onChange que o GenericForm espera
      onChange({
        target: {
          name: field.name,
          // Para o backend, enviamos o valor limpo (sem máscara). 
          // Se for Number Mask, enviamos o Number, senão a string limpa.
          value: finalValue,
        },
      });
    };

    // Verifica se é uma máscara numérica que usa vírgula como decimal (Number ou Currency)
    const isNumericMask = maskProps.mask === Number || formatMask === 'currency';

    // Remove 'value' das props para evitar conflito com 'unmaskedValue' no IMask
    const { value: _val, ...maskedProps } = props;

    // 🎯 CORREÇÃO: Usamos unmaskedValue com tratamento de string para garantir a formatação correta (PT-BR)
    const unmaskedValue = (value === '' || value == null) 
      ? '' 
      : (isNumericMask ? String(value).replace('.', ',') : String(value));

    // O MaskedInput usa 'onAccept' para retornar o valor limpo
    return (
      <MaskedInput
        {...maskedProps}
        unmaskedValue={unmaskedValue}
        // IMask espera o 'mask' prop para aplicar a máscara.
        mask={maskProps.mask || maskProps}
        // Handler para quando o valor limpo muda.
        onAccept={handleAccept}
        // Passa as props de configuração do IMask
        {...maskProps}
        // Sobrescreve o onChange para evitar conflito com o IMask
        onChange={() => { }}
      />
    );
  }

  // Se o metadado indicar que é uma chave estrangeira,
  // usamos o componente de busca assíncrona.
  if (field.foreign_key_model && field.foreign_key_label_field) {
    return <AsyncSelectInput {...props} value={value} />;
  }

  const fieldName = field.name.toLowerCase();
  if (
    fieldName.includes('password') ||
    fieldName.includes('senha') ||
    fieldName.includes('hashed')
  ) {
    return <PasswordInput {...props} value={value} />
  }

  switch (field.type) {
    case 'text':
    case 'email':
    case 'number':
      return <TextInput {...props} value={value} />
      
    case 'date':
    case 'datetime':
      return <DateInput {...props} value={value} />;

    case 'boolean':
      return <BooleanInput {...props} value={value} />;

    case 'select':
      return <SelectInput {...props} value={value} options={field.options} />;

    case 'creatable_select':
      return <CreatableSelectInput {...props} value={value} />;

    case 'rule_builder':
      return <RuleBuilderInput {...props} value={value} />;

    case 'order_items':
      return <OrderItemsInput {...props} value={value} />;

    default:
      console.warn(`Tipo de campo desconhecido: ${field.type}`);
      // Fallback para text
      return <TextInput {...props} value={value} />;
  }
};

export default FormRenderer;