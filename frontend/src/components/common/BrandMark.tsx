import { Box, HStack, Text } from '@chakra-ui/react';
import { Stethoscope } from '@/lib/icons';

interface BrandMarkProps {
  compact?: boolean;
}

export function BrandMark({ compact = false }: BrandMarkProps) {
  return (
    <HStack spacing={2.5} align="center" as="a" href="#/" aria-label="DR Support Screening home">
      <Box
        as="span"
        display="grid"
        placeItems="center"
        w="36px"
        h="36px"
        bg="brand.500"
        borderRadius="md"
        color="white"
        flexShrink={0}
      >
        <Stethoscope size={18} strokeWidth={2.25} aria-hidden="true" />
      </Box>
      {!compact && (
        <Box as="span" lineHeight="1.2">
          <Text fontSize="md" fontWeight="semibold" color="text.primary">
            DR Support
          </Text>
          <Text fontSize="xs" color="text.secondary" fontWeight="medium">
            Clinician review
          </Text>
        </Box>
      )}
    </HStack>
  );
}
