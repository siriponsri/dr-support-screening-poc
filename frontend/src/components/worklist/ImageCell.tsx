import { Box, HStack, Image, Stack, Text } from '@chakra-ui/react';
import { FileImage } from '@/lib/icons';
import type { CaseRecord } from '@/lib/api';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';

function admissionStatus(item: CaseRecord): { label: string; tone: StatusTone; note: string } | null {
  if (!item.admission_ui || ['Ready for analysis', 'Image type needs confirmation', 'Image type confirmed'].includes(item.admission_ui.label)) return null;
  return item.admission_ui;
}

export function ImageCell({ item, onQuickLook }: { item: CaseRecord; onQuickLook?: () => void }) {
  const status = admissionStatus(item);
  const filename = item.filename ?? item.display_name;
  return (
    <HStack spacing={3} minW={0}>
      {item.image_url ? (
        <Box
          as="button"
          type="button"
          onClick={onQuickLook}
          aria-label={`Quick look: ${filename}`}
          title="Quick look"
          flexShrink={0}
          borderRadius="sm"
          borderWidth="1px"
          borderColor="transparent"
          cursor={onQuickLook ? 'zoom-in' : 'default'}
          transition="border-color 150ms ease"
          _hover={{ borderColor: onQuickLook ? 'action.primary' : 'transparent' }}
          _focusVisible={{ boxShadow: 'focus', outline: 'none' }}
        >
          <Image src={item.image_url} alt={`${filename} retinal preview`} w="64px" h="48px" objectFit="contain" bg="surface.viewer" borderRadius="sm" />
        </Box>
      ) : (
        <Box aria-label="No image preview" w="64px" h="48px" flexShrink={0} bg="surface.subtle" borderRadius="sm" display="flex" alignItems="center" justifyContent="center" flexDirection="column" gap={1}>
          <FileImage size={16} aria-hidden="true" />
          <Text fontSize="xxs">No preview</Text>
        </Box>
      )}
      <Stack spacing={0.5} minW={0} flex={1}>
        <Text fontWeight="semibold" whiteSpace="nowrap" overflow="hidden" textOverflow="ellipsis" title={filename} tabIndex={0} _focusVisible={{ boxShadow: 'focus', borderRadius: 'sm', outline: 'none' }}>
          {filename}
        </Text>
        <StatusBadge tone={item.modality === 'UNKNOWN' ? 'warning' : 'neutral'} maxW="100%" whiteSpace="normal">{item.modality === 'CFP' ? 'CFP' : item.modality === 'UWF' ? 'UWF' : 'Image type needs confirmation'}</StatusBadge>
        {status && <Stack spacing={0} minW={0} title={status.note}><StatusBadge tone={status.tone} maxW="100%" whiteSpace="normal">{status.label}</StatusBadge><Text fontSize="xxs" color="text.secondary" noOfLines={1}>{status.note}</Text></Stack>}
      </Stack>
    </HStack>
  );
}
