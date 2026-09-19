/**
 * Placeholder — a small, restrained panel used by route placeholders that
 * have no real content yet. Conveys "this page is reserved" without
 * pretending to be production-ready.
 */
import { Box, HStack, Stack, Text } from '@chakra-ui/react';
import { Construction, type LucideIcon } from '@/lib/icons';
import { Section } from './Section';

interface PlaceholderProps {
  /** Title shown inside the panel; mirrors the page name. */
  title: string;
  /** A description line stating where the content will land next round. */
  message: string;
  /** Optional render hook callers can use to add detail (icons, list, etc.). */
  detail?: React.ReactNode;
  icon?: LucideIcon;
}

export function Placeholder({
  title,
  message,
  detail,
  icon: Icon = Construction,
}: PlaceholderProps) {
  return (
    <Section title={title} description="Reserved · migration in progress">
      <Box
        borderRadius="lg"
        borderWidth="1px"
        borderColor="border.subtle"
        borderStyle="dashed"
        bg="surface.subtle"
        p={{ base: 5, tablet: 6 }}
      >
        <HStack spacing={3} align="flex-start">
          <Box
            as="span"
            display="grid"
            placeItems="center"
            w="40px"
            h="40px"
            bg="surface.panel"
            borderRadius="md"
            borderWidth="1px"
            borderColor="border.subtle"
            color="brand.500"
            flexShrink={0}
          >
            <Icon size={20} strokeWidth={2} aria-hidden="true" />
          </Box>
          <Stack spacing={2} flex={1}>
            <Text fontSize="md" fontWeight="semibold" color="text.primary">
              {title}
            </Text>
            <Text fontSize="sm" color="text.secondary">
              {message}
            </Text>
            {detail && (
              <Box pt={2} color="text.secondary">
                {detail}
              </Box>
            )}
          </Stack>
        </HStack>
      </Box>
    </Section>
  );
}
