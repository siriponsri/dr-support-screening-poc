import { useId, useState } from 'react';
import { Box, Button, Collapse, HStack, Stack, Text } from '@chakra-ui/react';
import { ChevronDown, Info } from '@/lib/icons';
import { drGradeLabel } from '@/lib/api';

export interface GradeGuideEntry {
  grade: number;
  name: string;
  summary: string;
  detail?: string;
}

export const DR_GRADE_GUIDE: GradeGuideEntry[] = [
  {
    grade: 0,
    name: 'No apparent DR',
    summary: 'No diabetic-retinopathy abnormality is identified on the reviewable image.',
  },
  {
    grade: 1,
    name: 'Mild NPDR',
    summary: 'Microaneurysms only. Additional DR signs move the case beyond Mild NPDR.',
  },
  {
    grade: 2,
    name: 'Moderate NPDR',
    summary: 'More than microaneurysms alone (for example hemorrhages, hard exudates, or cotton-wool spots), but below Severe NPDR criteria.',
  },
  {
    grade: 3,
    name: 'Severe NPDR',
    summary: 'No proliferative signs, plus at least one ICO 4-2-1 criterion: >=20 intraretinal hemorrhages in each of 4 quadrants, definite venous beading in 2 quadrants, or IRMA in 1 quadrant.',
    detail: 'Any one of the three lesion-distribution thresholds is sufficient. Do not require all three thresholds simultaneously.',
  },
  {
    grade: 4,
    name: 'Proliferative DR (PDR)',
    summary: 'Proliferative disease with neovascularization and/or vitreous or preretinal hemorrhage.',
  },
];

export function GradeGuide() {
  const [open, setOpen] = useState(false);
  const contentId = useId();

  return (
    <Box>
      <Button
        size="sm"
        variant="ghost"
        leftIcon={<Info size={15} aria-hidden="true" />}
        rightIcon={<ChevronDown size={14} aria-hidden="true" />}
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((current) => !current)}
      >
        Grade guide
      </Button>
      <Collapse in={open} animateOpacity>
        <Box
          id={contentId}
          role="region"
          aria-label="ICO diabetic retinopathy grade guide"
          mt={3}
          p={3}
          borderWidth="1px"
          borderColor="border.default"
          borderRadius="md"
          bg="surface.subtle"
        >
          <Stack spacing={3}>
            {DR_GRADE_GUIDE.map((entry) => (
              <Box key={entry.grade}>
                <Text fontWeight="semibold" fontSize="sm">
                  {entry.grade} - {drGradeLabel(entry.grade) ?? entry.name}
                </Text>
                <Text fontSize="sm" color="text.secondary">{entry.summary}</Text>
                {entry.detail && <Text mt={1} fontSize="xs" color="text.secondary">{entry.detail}</Text>}
              </Box>
            ))}
            <HStack align="flex-start" spacing={2} pt={2} borderTopWidth="1px" borderColor="border.subtle">
              <Text fontSize="xs" color="text.secondary">
                Ungradable and Needs Second Review are workflow states outside the 0-4 severity grades. DME is a separate classification from DR grade.
              </Text>
            </HStack>
          </Stack>
        </Box>
      </Collapse>
    </Box>
  );
}

