import { Box, Heading, HStack, Text } from '@chakra-ui/react';
import type { ReactNode } from 'react';
import { useT } from '@/lib/i18n';

interface SectionProps {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}

export function Section({ title, description, action, children }: SectionProps) {
  const t = useT();   // Body text follows the EN/TH switch; titles stay English.
  return (
    <Box
      bg="surface.panel"
      minW={0}
      borderWidth="1px"
      borderColor="border.subtle"
      borderRadius="lg"
      boxShadow="xs"
      p={{ base: 4, laptop: 5 }}
    >
      <HStack
        justify="space-between"
        align="flex-start"
        mb={4}
        spacing={4}
        flexDirection={{ base: 'column', tablet: 'row' }}
      >
        <Box minW={0}>
          <Heading size="sm" mb={description ? 1 : 0}>
            {title}
          </Heading>
          {description && (
            <Text fontSize="sm" color="text.secondary">
              {typeof description === 'string' ? t(description) : description}
            </Text>
          )}
        </Box>
        {action && <Box width={{ base: '100%', tablet: 'auto' }} flexShrink={0}>{action}</Box>}
      </HStack>
      {children}
    </Box>
  );
}
