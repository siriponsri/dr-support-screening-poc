import { Box, Button, SimpleGrid, Text } from '@chakra-ui/react';
import { drGradeLabel } from '@/lib/api';
import { handleRadioArrowKeys, radioTabIndex } from '@/components/common/radioGroupKeys';

/** Selection value for Ungradable; it is a review state, not a DR severity. */
export const UNGRADABLE_CHOICE = 'UNGRADABLE';

const SHORT_LABELS: Record<string, string> = {
  0: 'No DR',
  1: 'Mild',
  2: 'Moderate',
  3: 'Severe',
  4: 'PDR',
};

interface GradeChoiceProps {
  labelId: string;
  value: string;
  onChange: (value: string) => void;
  isDisabled?: boolean;
}

/**
 * One-click DR grade selection. Selecting only fills the choice; the
 * clinician still confirms it with the page's confirm button. No grade is
 * preselected from the AI suggestion.
 */
export function GradeChoice({ labelId, value, onChange, isDisabled = false }: GradeChoiceProps) {
  const options = [
    ...[0, 1, 2, 3, 4].map((grade) => ({
      value: String(grade),
      mark: String(grade),
      label: SHORT_LABELS[grade],
      name: `${grade} ${drGradeLabel(grade)}`,
    })),
    { value: UNGRADABLE_CHOICE, mark: 'U', label: 'Ungradable', name: 'Ungradable' },
  ];
  const values = options.map((option) => option.value);
  return (
    <SimpleGrid
      role="radiogroup"
      aria-labelledby={labelId}
      // Three per row: the clinician panel is narrow, so six columns clipped the labels.
      columns={3}
      spacing={2}
      onKeyDown={(event) => { if (!isDisabled) handleRadioArrowKeys(event, values, value, onChange); }}
    >
      {options.map((option) => {
        const selected = value === option.value;
        const ungradable = option.value === UNGRADABLE_CHOICE;
        return (
          <Button
            key={option.value}
            role="radio"
            aria-checked={selected}
            tabIndex={radioTabIndex(values, value, option.value)}
            aria-label={option.name}
            title={option.name}
            isDisabled={isDisabled}
            onClick={() => onChange(option.value)}
            variant="outline"
            h="60px"
            px={1}
            flexDirection="column"
            gap={0.5}
            bg={selected ? 'action.primary' : 'surface.panel'}
            color={selected ? 'text.inverse' : 'text.primary'}
            borderColor={selected ? 'action.primary' : ungradable ? 'border.strong' : 'border.default'}
            borderStyle={ungradable && !selected ? 'dashed' : 'solid'}
            transition="background 150ms ease, color 150ms ease, border-color 150ms ease"
            _hover={{ bg: selected ? 'action.primaryHover' : 'surface.subtle' }}
          >
            <Box as="span" fontSize="xl" fontWeight="semibold" lineHeight="1">{option.mark}</Box>
            <Text as="span" fontSize="xs" fontWeight="medium" color="inherit" whiteSpace="normal" textAlign="center" lineHeight="short">{option.label}</Text>
          </Button>
        );
      })}
    </SimpleGrid>
  );
}
