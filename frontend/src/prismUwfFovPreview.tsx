import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ChakraProvider, Box, Text } from '@chakra-ui/react';
import {
  PrismAnalysisFieldOverlay,
  type PrismFovStatus,
} from '@/components/review/PrismAnalysisFieldOverlay';
import evidence from '@/prismUwfFovPreviewEvidence.json';
import { theme } from '@/theme';

const boundary = evidence.boundary.map(([x, y]) => [x, y] as const);
const fixtureBaseUrl = `${import.meta.env.BASE_URL}prism-uwf-fov-preview/`;
const status: PrismFovStatus = evidence.status === 'READY'
  ? 'READY'
  : evidence.status === 'UNCERTAIN' ? 'UNCERTAIN' : 'UNAVAILABLE';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ChakraProvider theme={theme}>
      <Box minH="100vh" bg="surface.canvas" p={{ base: 3, md: 6 }}>
        <Box maxW="960px" mx="auto">
          <Text fontSize="xs" color="text.secondary" mb={2}>
            Synthetic detector fixture
          </Text>
          <PrismAnalysisFieldOverlay
            imageUrl={`${fixtureBaseUrl}original.png`}
            imageWidth={512}
            imageHeight={512}
            status={status}
            fieldMaskImageUrl={`${fixtureBaseUrl}field-mask.png`}
            maskSha256={evidence.maskSha256}
            maskVersion={evidence.maskVersion}
            excludedFraction={evidence.excludedFraction}
            boundary={boundary}
          />
        </Box>
      </Box>
    </ChakraProvider>
  </StrictMode>,
);
