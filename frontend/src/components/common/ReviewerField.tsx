import { Checkbox, FormControl, FormLabel, Input, Stack, Text } from '@chakra-ui/react';

interface ReviewerFieldProps {
  id: string;
  value: string;
  useAsDefault: boolean;
  onChange: (value: string) => void;
  onUseAsDefaultChange: (checked: boolean) => void;
  required?: boolean;
  helpText?: string;
}

export function ReviewerField({
  id,
  value,
  useAsDefault,
  onChange,
  onUseAsDefaultChange,
  required = true,
  helpText,
}: ReviewerFieldProps) {
  return (
    <FormControl isRequired={required}>
      <FormLabel htmlFor={id}>Reviewer name</FormLabel>
      <Stack spacing={2}>
        <Input
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Reviewer name"
          autoComplete="name"
        />
        <Checkbox
          isChecked={useAsDefault}
          onChange={(event) => onUseAsDefaultChange(event.target.checked)}
        >
          Use as default reviewer on this workstation
        </Checkbox>
        {helpText && <Text fontSize="xs" color="text.secondary">{helpText}</Text>}
      </Stack>
    </FormControl>
  );
}
