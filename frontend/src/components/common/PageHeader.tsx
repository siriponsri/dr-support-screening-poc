/**
 * PageHeader — the in-content title used at the top of every page.
 *
 * Different from the AppHeader (which is the chrome-level top bar).
 * Pages render their own PageHeader so in-content copy can grow
 * without crowding the chrome.
 */
import { Box, Heading, HStack, Stack, Text } from '@chakra-ui/react';
import type { ReactNode } from 'react';
import { getRouteMeta } from '@/components/shell/routeMeta';

interface PageHeaderProps {
  /** Pathname the page is mounted at — drives the default title/subtitle. */
  pathname?: string;
  /** Override the routed title if the page renders a more specific one. */
  title?: string;
  subtitle?: string;
  kicker?: string;
  /** Right-aligned actions (e.g. buttons). */
  actions?: ReactNode;
}

export function PageHeader({
  pathname,
  title,
  subtitle,
  kicker,
  actions,
}: PageHeaderProps) {
  const meta = getRouteMeta(pathname ?? '');
  const resolvedTitle = title ?? meta.title;
  const resolvedSubtitle = subtitle ?? meta.subtitle;
  const resolvedKicker = kicker ?? meta.kicker;

  return (
    <Stack spacing={1.5} mb={6}>
      {resolvedKicker && (
        <Text
          fontSize="xxs"
          fontWeight="bold"
          letterSpacing="0.16em"
          textTransform="uppercase"
          color="action.primary"
        >
          {resolvedKicker}
        </Text>
      )}
      <HStack spacing={3} align="flex-end" justify="space-between">
        <Box minW={0}>
          <Heading
            as="h1"
            size={{ base: '2xl', tablet: '3xl' }}
            letterSpacing="-0.02em"
            noOfLines={2}
          >
            {resolvedTitle}
          </Heading>
          {resolvedSubtitle && (
            <Text
              fontSize={{ base: 'sm', tablet: 'md' }}
              color="text.secondary"
              mt={1}
              maxW="780px"
            >
              {resolvedSubtitle}
            </Text>
          )}
        </Box>
        {actions && <Box flexShrink={0}>{actions}</Box>}
      </HStack>
    </Stack>
  );
}
