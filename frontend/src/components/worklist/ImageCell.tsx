import { Box, HStack, Image, Stack, Text } from '@chakra-ui/react';
import { FileImage } from '@/lib/icons';
import type { CaseRecord } from '@/lib/api';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';

function admissionStatus(item: CaseRecord): { label: string; tone: StatusTone; note: string } | null {
  if (!item.admission_ui || item.admission_ui.label === 'Ready for analysis') return null;
  return item.admission_ui;
}

export function ImageCell({ item }: { item: CaseRecord }) {
  const status = admissionStatus(item);
  const filename = item.filename ?? item.display_name;
  return (
    <HStack spacing={3} minW={0}>
      {item.image_url ? (
        <Image src={item.image_url} alt={`${filename} retinal preview`} w="64px" h="48px" flexShrink={0} objectFit="contain" bg="surface.viewer" borderRadius="sm" />
      ) : (
        <Box aria-label="No image preview" w="64px" h="48px" flexShrink={0} bg="surface.subtle" borderRadius="sm" display="flex" alignItems="center" justifyContent="center" flexDirection="column" gap={1}>
          <FileImage size={16} aria-hidden="true" />
          <Text fontSize="xxs">No preview</Text>
        </Box>
      )}
      <Stack spacing={0.5} minW={0}>
        <Text fontWeight="semibold" whiteSpace="nowrap" overflow="hidden" textOverflow="ellipsis" title={filename} tabIndex={0} _focusVisible={{ boxShadow: 'focus', borderRadius: 'sm', outline: 'none' }}>
          {filename}
        </Text>
        {status && <Stack spacing={0} minW={0} title={status.note}><StatusBadge tone={status.tone}>{status.label}</StatusBadge><Text fontSize="xxs" color="text.secondary" noOfLines={1}>{status.note}</Text></Stack>}
      </Stack>
    </HStack>
  );
}
