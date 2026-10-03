import { Button, Checkbox, FormControl, FormLabel, HStack, Input, Stack, Text } from '@chakra-ui/react';
import { useState } from 'react';

interface ReviewerFieldProps {
  id: string;
  value: string;
  useAsDefault: boolean;
  onChange: (value: string) => void;
  onUseAsDefaultChange: (checked: boolean) => void;
  required?: boolean;
  helpText?: string;
  compact?: boolean;
}

export function ReviewerField({
  id,
  value,
  useAsDefault,
  onChange,
  onUseAsDefaultChange,
  required = true,
  helpText,
  compact = false,
}: ReviewerFieldProps) {
  const [editing, setEditing] = useState(false);
  if (compact && value.trim() && useAsDefault && !editing) {
    return (
      <Stack spacing={1}>
        <HStack spacing={3} align="center">
          <Text fontSize="sm"><Text as="span" color="text.secondary">Reviewer:</Text> {value.trim()}</Text>
          <Button type="button" size="xs" variant="ghost" onClick={() => setEditing(true)}>Change</Button>
        </HStack>
        {helpText && <Text fontSize="xs" color="text.secondary">{helpText}</Text>}
      </Stack>
    );
  }
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
        {compact && value.trim() && <Button type="button" size="xs" variant="ghost" alignSelf="flex-start" onClick={() => setEditing(false)}>Use this reviewer</Button>}
      </Stack>
    </FormControl>
  );
}
