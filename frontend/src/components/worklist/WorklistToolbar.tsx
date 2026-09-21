import {
  Button,
  ButtonGroup,
  Divider,
  HStack,
  Input,
  InputGroup,
  InputLeftElement,
  Popover,
  PopoverArrow,
  PopoverBody,
  PopoverCloseButton,
  PopoverContent,
  PopoverHeader,
  PopoverTrigger,
  Radio,
  RadioGroup,
  Stack,
  Text,
} from '@chakra-ui/react';
import { Filter, Search } from '@/lib/icons';
import type { AiFilter, ReadinessFilter, ReviewFilter, SortOption, ViewMode, WorklistFilters } from './worklistModel';
import type { ReactNode } from 'react';

interface WorklistToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  filters: WorklistFilters;
  onFiltersChange: (filters: WorklistFilters) => void;
  sort: SortOption;
  onSortChange: (sort: SortOption) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
}

const sortLabels: Record<SortOption, string> = {
  filename: 'Filename',
  'patient-eye': 'Patient / eye',
  review: 'Review status',
  recent: 'Recently updated',
};

function FilterSection({ title, children }: { title: string; children: ReactNode }) {
  return <Stack spacing={2}><Text fontSize="xs" fontWeight="semibold" color="text.secondary">{title}</Text>{children}</Stack>;
}

export function WorklistToolbar({ search, onSearchChange, filters, onFiltersChange, sort, onSortChange, viewMode, onViewModeChange }: WorklistToolbarProps) {
  const activeFilterCount = Object.values(filters).filter((value) => value !== 'all').length;
  const updateFilter = <Key extends keyof WorklistFilters>(key: Key, value: WorklistFilters[Key]) => {
    onFiltersChange({ ...filters, [key]: value });
  };

  return (
    <Stack spacing={3} mb={4}>
      <HStack spacing={2} align="stretch" flexWrap="wrap">
        <InputGroup size="sm" flex={{ base: '1 1 100%', tablet: '1 1 260px' }} maxW={{ tablet: '360px' }}>
          <InputLeftElement pointerEvents="none"><Search size={15} aria-hidden="true" /></InputLeftElement>
          <Input value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search filename or patient key" aria-label="Search worklist" pl={9} />
        </InputGroup>
        <Popover placement="bottom-start" closeOnBlur>
          <PopoverTrigger>
            <Button size="sm" variant="outline" leftIcon={<Filter size={15} />} aria-label="Open filters">
              Filters{activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}
            </Button>
          </PopoverTrigger>
          <PopoverContent width="280px">
            <PopoverArrow /><PopoverCloseButton /><PopoverHeader fontWeight="semibold">Filter worklist</PopoverHeader>
            <PopoverBody><Stack spacing={4}>
              <FilterSection title="Readiness">
                <RadioGroup value={filters.readiness} onChange={(value) => updateFilter('readiness', value as ReadinessFilter)}>
                  <Stack spacing={2}><Radio value="all">All</Radio><Radio value="identity">Needs patient / eye confirmation</Radio><Radio value="image">Needs image review</Radio><Radio value="ready">Ready</Radio></Stack>
                </RadioGroup>
              </FilterSection>
              <Divider />
              <FilterSection title="Review">
                <RadioGroup value={filters.review} onChange={(value) => updateFilter('review', value as ReviewFilter)}>
                  <Stack spacing={2}><Radio value="all">All</Radio><Radio value="pending">Pending</Radio><Radio value="reviewed">Reviewed</Radio><Radio value="excluded">Excluded</Radio></Stack>
                </RadioGroup>
              </FilterSection>
              <Divider />
              <FilterSection title="AI">
                <RadioGroup value={filters.ai} onChange={(value) => updateFilter('ai', value as AiFilter)}>
                  <Stack spacing={2}><Radio value="all">All</Radio><Radio value="analyzed">Analyzed</Radio><Radio value="not-analyzed">Not analyzed</Radio><Radio value="unavailable">AI unavailable</Radio></Stack>
                </RadioGroup>
              </FilterSection>
              {activeFilterCount > 0 && <Button size="sm" variant="ghost" alignSelf="flex-start" onClick={() => onFiltersChange({ readiness: 'all', review: 'all', ai: 'all' })}>Clear filters</Button>}
            </Stack></PopoverBody>
          </PopoverContent>
        </Popover>
        <Popover placement="bottom-start" closeOnBlur>
          <PopoverTrigger><Button size="sm" variant="outline">Sort: {sortLabels[sort]}</Button></PopoverTrigger>
          <PopoverContent width="220px"><PopoverArrow /><PopoverCloseButton /><PopoverHeader fontWeight="semibold">Sort worklist</PopoverHeader><PopoverBody>
            <RadioGroup value={sort} onChange={(value) => onSortChange(value as SortOption)}><Stack spacing={2}>{Object.entries(sortLabels).map(([value, label]) => <Radio key={value} value={value}>{label}</Radio>)}</Stack></RadioGroup>
          </PopoverBody></PopoverContent>
        </Popover>
        <ButtonGroup size="sm" isAttached ml={{ tablet: 'auto' }} aria-label="Worklist view">
          <Button variant={viewMode === 'cases' ? 'solid' : 'outline'} aria-pressed={viewMode === 'cases'} onClick={() => onViewModeChange('cases')}>Cases</Button>
          <Button variant={viewMode === 'patients' ? 'solid' : 'outline'} aria-pressed={viewMode === 'patients'} onClick={() => onViewModeChange('patients')}>Patients</Button>
        </ButtonGroup>
      </HStack>
      <Text color="text.secondary" fontSize="sm">Search by filename or pseudonymous patient key.</Text>
    </Stack>
  );
}
