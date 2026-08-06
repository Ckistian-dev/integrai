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
  OrderItemsInput,
  FileInput,
  DefaultFiltersInput,
  MultiSelectInput,
  TextAreaInput,
  ImageUploadOrUrlInput,
  ColorInput
} from '../ui/InputFields';
import { RuleBuilderInput } from '../ui/RuleBuilderInput';
import { CreatableSelectInput } from '../ui/CreatableSelectInput';
import { StateTaxRulesInput } from '../ui/StateTaxRulesInput';
import { PermissionsBuilderInput } from '../ui/PermissionsBuilderInput';
import { ReportBuilderInput } from '../ui/ReportBuilderInput';
import { PaymentMethodsInput } from '../ui/PaymentMethodsInput';
import { MeliStatusRulesInput } from '../ui/MeliStatusRulesInput';
import { PackagingSimulationInput } from '../ui/PackagingSimulationInput';

/**
 * Componente FormRenderer
 * Renderiza o input correto baseado nos metadados do campo.
 */
const FormRenderer = ({ field, value, onChange, error, modelName, formData, ...rest }) => {
  // Se o campo estiver explicitamente marcado como não visível, não renderiza
  if (field.visible === false) {
    return null;
  }

  // Estado para controlar se o campo está focado
  const [isFocused, setIsFocused] = React.useState(false);

  const props = {
    field,
    value: value ?? '',
    onChange,
    error,
    modelName,
    formData,
    disabled: field.read_only,
    ...rest,
  };

  const formatMask = field.format_mask;
  const maskProps = (field.type !== 'date' && field.type !== 'datetime' && formatMask)
    ? MASKS[formatMask]
    : null;

  // Handlers para controlar o foco
  const handleFocus = (e) => {
    setIsFocused(true);
    if (Number(value) === 0 && e && e.target && e.target.select) {
      setTimeout(() => e.target.select(), 10);
    }
  };
  const handleBlur = () => setIsFocused(false);

  if (maskProps) {
    // 1. Lógica de SAÍDA (O que vai para o state/banco quando edita)
    const handleAccept = (val, maskRef) => {
      let finalValue = maskRef.unmaskedValue;
      
      // Se for Moeda/Decimal, converte de volta para Number (ex: "1.000,50" -> 1000.5)
      if (maskProps.mask === Number || formatMask === 'currency') {
        if (finalValue !== '') {
          if (typeof maskRef.typedValue === 'number') {
            finalValue = maskRef.typedValue;
          } else {
            finalValue = parseFloat(String(finalValue).replace(',', '.'));
          }
          if (isNaN(finalValue)) finalValue = null;
        } else {
          finalValue = null;
        }
      } else if (typeof maskProps === 'string' || Array.isArray(maskProps)) {
        // Se for CPF/CNPJ, limpa tudo e deixa só caracteres alfanuméricos
        if (finalValue) finalValue = finalValue.replace(/[^a-zA-Z0-9]/g, '').toUpperCase(); 
        if (finalValue === '') finalValue = null;
      }

      onChange({
        target: { name: field.name, value: finalValue },
      });
    };

    const { ...maskedProps } = props; 

    // Detecta se é numérico apenas para saber se precisamos trocar ponto por vírgula
    const isNumericMask = (formatMask === 'currency' || 
                           formatMask.startsWith('decimal') || 
                           formatMask.startsWith('percent') ||
                           maskProps.mask === Number);

    // Params básicos
    let imaskParams = {
      ...maskedProps,
      ...maskProps,
      mask: maskProps.mask || maskProps,
      onAccept: handleAccept,
      onChange: () => {} 
    };

    // 2. Lógica de ENTRADA (Banco -> Visual)
    // MANTIDO: Usando 'value' como você pediu
    if (isNumericMask) {
      let stringValue = '';

      if (value !== null && value !== undefined && value !== '') {
        // 🔥 AQUI ESTÁ A CORREÇÃO PARA 89.73:
        // Convertemos para Number e usamos toFixed(2) para garantir o formato "89.73".
        // Se usássemos String(89.73) direto, funcionaria, mas toFixed é mais seguro para arredondamentos.
        const numVal = Number(value);
        if (!isNaN(numVal)) {
          // Tenta pegar a escala da máscara ou usa 2 como padrão
          // FIX: Currency tem scale dentro de blocks.num
          const scale = maskProps.scale || maskProps.blocks?.num?.scale || 2; 
          
          // FIX: Currency tem padFractionalZeros dentro de blocks.num
          const padZeros = maskProps.padFractionalZeros !== undefined 
            ? maskProps.padFractionalZeros 
            : (maskProps.blocks?.num?.padFractionalZeros !== undefined ? maskProps.blocks.num.padFractionalZeros : true);

          // Lógica Híbrida:
          // Se padFractionalZeros for false (ex: percentual ou moeda), formatamos com zeros APENAS no Blur.
          // Quando focado, deixamos como string simples para permitir digitar a vírgula livremente.
          if (padZeros === false) {
            if (isFocused) {
              // Se focado, não definimos stringValue aqui para não sobrescrever o buffer do IMask.
              // O controle será feito abaixo, passando undefined para o value.
            } else {
              stringValue = numVal.toFixed(scale); // Formata (ex: 10,00) ao sair
            }
          } else {
            stringValue = numVal.toFixed(scale); // Gera "89.73"
          }
        } else {
          stringValue = String(value);
        }

        // Trocamos o PONTO pela VÍRGULA (o truque que fez funcionar antes)
        // "89.73" vira "89,73"
        stringValue = stringValue.replace('.', ',');
      }

      // Passamos para VALUE (como estava funcionando)
      // Se estiver focado e for um campo livre (padFractionalZeros=false), passamos undefined
      // para que o IMask mantenha o que o usuário está digitando (ex: "10,")
      
      // Recalcula ou reutiliza a lógica de padZeros
      const padZeros = maskProps.padFractionalZeros !== undefined 
            ? maskProps.padFractionalZeros 
            : (maskProps.blocks?.num?.padFractionalZeros !== undefined ? maskProps.blocks.num.padFractionalZeros : true);

      if (padZeros === false && isFocused) {
        imaskParams.value = undefined;
      } else {
        imaskParams.value = stringValue;
      }
      
      // Limpamos o resto
      imaskParams.unmaskedValue = undefined;
      imaskParams.typedValue = undefined;
      imaskParams.onFocus = handleFocus;
      imaskParams.onBlur = handleBlur;

    } else {
      // Para CPF/CNPJ (Texto)
      // Aqui usamos value direto pois a máscara é simples (substituição de char)
      imaskParams.value = String(value || '');
      imaskParams.unmaskedValue = undefined; 
      imaskParams.typedValue = undefined;
    }

    // Key para garantir que o React renderize o input APÓS os dados chegarem
    // FIX: Usar apenas o nome do campo para evitar que o input seja recriado (perda de foco) ao digitar
    const forceRenderKey = field.name;

    return <MaskedInput key={forceRenderKey} {...imaskParams} />;
  }

  // Se o metadado indicar que é uma chave estrangeira,
  // usamos o componente de busca assíncrona.
  if (field.foreign_key_model && field.foreign_key_label_field) {
    // Forçar a re-renderização (e limpeza de cacheOptions do AsyncSelect) se for plano de contas e o tipo_conta mudar
    let selectKey = field.name;
    if (modelName === 'contas' && field.name === 'id_classificacao_contabil') {
      selectKey = `${field.name}-${formData?.tipo_conta}`;
    }
    return <AsyncSelectInput key={selectKey} {...props} value={value} />;
  }

  if (field.type === 'hidden') {
    return null;
  }

  const fieldName = field.name.toLowerCase();
  if (
    field.ui_type === 'password' ||
    fieldName.includes('password') ||
    fieldName.includes('senha') ||
    fieldName.includes('hashed') ||
    fieldName.includes('secret') ||
    fieldName.includes('key') ||
    fieldName.includes('token')
  ) {
    return <PasswordInput {...props} value={value} />
  }

  if (
    field.type === 'color' ||
    field.ui_type === 'color' ||
    fieldName === 'cor' ||
    fieldName === 'color' ||
    fieldName.includes('cor_') ||
    fieldName.includes('_cor') ||
    fieldName.includes('color_') ||
    fieldName.includes('_color') ||
    fieldName.includes('sidebar')
  ) {
    return <ColorInput {...props} value={value} />;
  }

  switch (field.type) {
    case 'color':
      return <ColorInput {...props} value={value} />;

    case 'text':
    case 'email':
    case 'number':
      return <TextInput {...props} value={value} />
      
    case 'textarea':
      return <TextAreaInput {...props} value={value} />
      
    case 'date':
    case 'datetime':
      return <DateInput {...props} value={value} />;

    case 'boolean':
      return <BooleanInput {...props} value={value} />;

    case 'image_upload_or_url':
      return <ImageUploadOrUrlInput {...props} value={value} />;

    case 'file':
      return <FileInput {...props} value={value} fileName={field.filename_field ? formData[field.filename_field] : null} />;

    case 'select':
      return <SelectInput {...props} value={value} options={field.options} />;

    case 'multiselect':
      return <MultiSelectInput {...props} value={value} options={field.options} />;

    case 'creatable_select':
      return <CreatableSelectInput {...props} value={value} />;

    case 'rule_builder':
      return <RuleBuilderInput {...props} value={value} />;

    case 'packaging_simulation':
      return <PackagingSimulationInput {...props} value={value} formData={formData} />;

    case 'state_tax_rules':
      return <StateTaxRulesInput {...props} value={value} />;

    case 'permissions_builder':
      return <PermissionsBuilderInput {...props} value={value} />;

    case 'report_builder':
      return <ReportBuilderInput {...props} value={value} formData={formData} />;

    case 'filtros_padrao':
      return <DefaultFiltersInput {...props} value={value} options={field.options} />;

    case 'order_items':
      return <OrderItemsInput {...props} value={value} />;

    case 'payment_methods':
      return <PaymentMethodsInput {...props} value={value} formData={formData} />;

    case 'meli_status_rules':
      return <MeliStatusRulesInput {...props} value={value} />;

    default:
      if (field.component === 'payment_methods') {
        return <PaymentMethodsInput {...props} value={value} formData={formData} />;
      }
      return <TextInput {...props} value={value} />;
  }
};

export default FormRenderer;