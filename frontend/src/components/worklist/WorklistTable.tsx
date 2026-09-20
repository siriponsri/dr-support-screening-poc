import { Table, TableContainer, Tbody, Td, Th, Thead, Tr } from '@chakra-ui/react';
import type { CaseRecord } from '@/lib/api';
import { AIResultCell } from './AIResultCell';
import { ImageCell } from './ImageCell';
import { PatientEyeCell } from './PatientEyeCell';
import { ReviewActionCell } from './ReviewActionCell';
import { ReviewStatusCell } from './ReviewStatusCell';

export function WorklistTable({ cases, onResolve, onQueueAction }: { cases: CaseRecord[]; onResolve: (item: CaseRecord) => void; onQueueAction: (item: CaseRecord, action: 'EXCLUDE' | 'RESTORE') => void }) {
  return (
    <TableContainer overflowX="auto" maxW="100%">
      <Table variant="clinical" size="sm" layout="fixed" w="100%" minW={{ base: '720px', tablet: '0' }} sx={{ tableLayout: 'fixed' }}>
        <Thead><Tr><Th w={{ base: '31%', desktop: '30%' }}>Image</Th><Th w={{ base: '24%', desktop: '23%' }}>Patient / eye</Th><Th w={{ base: '16%', desktop: '16%' }}>AI result</Th><Th w={{ base: '16%', desktop: '16%' }}>Review</Th><Th w={{ base: '13%', desktop: '15%' }} isNumeric>Action</Th></Tr></Thead>
        <Tbody>{cases.map((item) => (
          <Tr key={item.image_id} data-testid={`case-row-${item.display_name}`} opacity={item.queue_state === 'EXCLUDED' ? 0.62 : 1} bg={item.queue_state === 'EXCLUDED' ? 'surface.subtle' : undefined} title={item.queue_state === 'EXCLUDED' ? 'Excluded from queue. Restore to return this case to the worklist.' : undefined}>
            <Td><ImageCell item={item} /></Td><Td><PatientEyeCell item={item} onResolve={() => onResolve(item)} /></Td><Td><AIResultCell item={item} /></Td><Td><ReviewStatusCell item={item} /></Td><Td isNumeric whiteSpace="nowrap"><ReviewActionCell item={item} onQueueAction={(action) => onQueueAction(item, action)} /></Td>
          </Tr>
        ))}</Tbody>
      </Table>
    </TableContainer>
  );
}
