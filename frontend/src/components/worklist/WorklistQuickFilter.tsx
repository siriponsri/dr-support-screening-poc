import { Box, Button, HStack, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord } from '@/lib/api';
import { finalGradeKey, workStatus, type FinalGradeFilter, type StatusFilter } from './worklistModel';

interface WorklistQuickFilterProps {
  cases: CaseRecord[];
  status: StatusFilter;
  onStatusChange: (status: StatusFilter) => void;
  finalGrade: FinalGradeFilter;
  onFinalGradeChange: (grade: FinalGradeFilter) => void;
}

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'not-started', label: 'Not started' },
  { value: 'in-progress', label: 'In progress' },
  { value: 'done', label: 'Done' },
];

const GRADE_OPTIONS: { value: FinalGradeFilter; label: string }[] = [
  { value: 'all', label: 'All grades' },
  { value: '0', label: 'Grade 0' },
  { value: '1', label: 'Grade 1' },
  { value: '2', label: 'Grade 2' },
  { value: '3', label: 'Grade 3' },
  { value: '4', label: 'Grade 4' },
  { value: 'U', label: 'Ungradable' },
];

function Chip({ label, count, selected, onClick }: { label: string; count: number; selected: boolean; onClick: () => void }) {
  return (
    <Button
      size="sm"
      variant="outline"
      aria-pressed={selected}
      onClick={onClick}
      bg={selected ? 'action.primary' : 'surface.panel'}
      color={selected ? 'text.inverse' : 'text.primary'}
      borderColor={selected ? 'action.primary' : 'border.default'}
      borderRadius="sm"
      transition="background 150ms ease, color 150ms ease, border-color 150ms ease"
      _hover={{ bg: selected ? 'action.primaryHover' : 'surface.subtle' }}
    >
      {label}
      <Box as="span" ml={2} sx={{ fontVariantNumeric: 'tabular-nums' }} color={selected ? 'text.inverse' : 'text.secondary'} fontWeight="medium">{count}</Box>
    </Button>
  );
}

/** Status-first quick filter; done cases can be narrowed by the clinician's final grade. */
export function WorklistQuickFilter({ cases, status, onStatusChange, finalGrade, onFinalGradeChange }: WorklistQuickFilterProps) {
  const active = cases.filter((item) => workStatus(item) !== 'excluded');
  const statusCount = (value: StatusFilter) => value === 'all' ? cases.length : active.filter((item) => workStatus(item) === value).length;
  const done = active.filter((item) => workStatus(item) === 'done');
  const gradeCount = (value: FinalGradeFilter) => value === 'all' ? done.length : done.filter((item) => finalGradeKey(item) === value).length;
  return (
    <Stack spacing={2} mb={3}>
      <HStack role="group" aria-label="Filter by status" spacing={2} flexWrap="wrap">
        {STATUS_OPTIONS.map((option) => (
          <Chip key={option.value} label={option.label} count={statusCount(option.value)} selected={status === option.value}
            onClick={() => { onStatusChange(option.value); if (option.value !== 'done') onFinalGradeChange('all'); }} />
        ))}
      </HStack>
      {status === 'done' && (
        <HStack role="group" aria-label="Filter done cases by final grade" spacing={2} flexWrap="wrap" pl={{ tablet: 1 }}>
          <Text fontSize="xs" color="text.secondary" mr={1}>Final grade</Text>
          {GRADE_OPTIONS.map((option) => (
            <Chip key={option.value} label={option.label} count={gradeCount(option.value)} selected={finalGrade === option.value}
              onClick={() => onFinalGradeChange(option.value)} />
          ))}
        </HStack>
      )}
    </Stack>
  );
}
