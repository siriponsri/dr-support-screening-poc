import { Box, HStack, Image, Text } from '@chakra-ui/react';
import logoUrl from '@/assets/dr-support-logo.svg';

interface BrandMarkProps {
  compact?: boolean;
}

export function BrandMark({ compact = false }: BrandMarkProps) {
  return (
    <HStack spacing={2.5} align="center" as="a" href="#/" aria-label="Retinal Review Workbench home">
      <Image src={logoUrl} alt="" w="36px" h="36px" borderRadius="full" flexShrink={0} />
      {!compact && (
        <Box as="span" lineHeight="1.2">
          <Text fontSize="md" fontWeight="semibold" color="text.primary">
            Retinal Review
          </Text>
          <Text fontSize="xs" color="text.secondary" fontWeight="medium">
            Workbench
          </Text>
        </Box>
      )}
    </HStack>
  );
}
