import { HStack, Table, TableContainer, Tbody, Td, Th, Thead, Tr, Text } from '@chakra-ui/react';
import { Fragment } from 'react';
import type { CaseRecord, ModelDescriptor } from '@/lib/api';
import { AIResultCell } from './AIResultCell';
import { ImageCell } from './ImageCell';
import { PatientEyeCell } from './PatientEyeCell';
import { ReviewActionCell } from './ReviewActionCell';
import { ReviewStatusCell } from './ReviewStatusCell';
import type { PatientGroup } from './worklistModel';

interface WorklistTableProps {
  cases: CaseRecord[];
  groups?: PatientGroup[];
  models?: ModelDescriptor[];
  onResolve: (item: CaseRecord) => void;
  onReadiness: (item: CaseRecord) => void;
  onConfirmImage: (item: CaseRecord) => void;
  onQueueAction: (item: CaseRecord, action: 'EXCLUDE' | 'RESTORE') => void;
  onQuickLook?: (item: CaseRecord) => void;
}

function CaseRow({ item, models, onResolve, onReadiness, onConfirmImage, onQueueAction, onQuickLook }: { item: CaseRecord; models: ModelDescriptor[]; onResolve: (item: CaseRecord) => void; onReadiness: (item: CaseRecord) => void; onConfirmImage: (item: CaseRecord) => void; onQueueAction: (item: CaseRecord, action: 'EXCLUDE' | 'RESTORE') => void; onQuickLook?: (item: CaseRecord) => void }) {
  return (
    <Tr key={item.image_id} data-testid={`case-row-${item.display_name}`} opacity={item.queue_state === 'EXCLUDED' ? 0.62 : 1} bg={item.queue_state === 'EXCLUDED' ? 'surface.subtle' : undefined} title={item.queue_state === 'EXCLUDED' ? 'Excluded from queue. Restore to return this case to the worklist.' : undefined}>
      <Td><ImageCell item={item} onQuickLook={onQuickLook ? () => onQuickLook(item) : undefined} /></Td><Td><PatientEyeCell item={item} onResolve={() => onResolve(item)} /></Td><Td><AIResultCell item={item} models={models} /></Td><Td><ReviewStatusCell item={item} /></Td><Td isNumeric whiteSpace="nowrap"><ReviewActionCell item={item} onResolve={() => onResolve(item)} onReadiness={() => onReadiness(item)} onConfirmImage={() => onConfirmImage(item)} onQueueAction={(action) => onQueueAction(item, action)} /></Td>
    </Tr>
  );
}

function PatientGroupRows({ group, models, onResolve, onReadiness, onConfirmImage, onQueueAction, onQuickLook }: { group: PatientGroup; models: ModelDescriptor[]; onResolve: (item: CaseRecord) => void; onReadiness: (item: CaseRecord) => void; onConfirmImage: (item: CaseRecord) => void; onQueueAction: (item: CaseRecord, action: 'EXCLUDE' | 'RESTORE') => void; onQuickLook?: (item: CaseRecord) => void }) {
  return <>
    <Tr data-testid={`patient-group-${group.key ? group.label : 'unlinked'}`}><Td colSpan={5} bg="surface.subtle" py={3}><HStack justify="space-between"><Text fontWeight="semibold">{group.label}</Text><Text fontSize="xs" color="text.secondary">{group.eyes.reduce((count, eye) => count + eye.cases.length, 0)} {group.eyes.reduce((count, eye) => count + eye.cases.length, 0) === 1 ? 'image' : 'images'}</Text></HStack></Td></Tr>
    {group.eyes.map((eye) => <Fragment key={`${group.key ?? 'unlinked'}-${eye.laterality}`}><Tr><Td colSpan={5} py={2} pl={7} borderBottomWidth="0"><Text fontSize="sm" color="text.secondary" fontWeight="semibold">{eye.label}</Text></Td></Tr>{eye.cases.map((item) => <CaseRow key={item.image_id} item={item} models={models} onResolve={onResolve} onReadiness={onReadiness} onConfirmImage={onConfirmImage} onQueueAction={onQueueAction} onQuickLook={onQuickLook} />)}</Fragment>)}
  </>;
}

export function WorklistTable({ cases, groups, models = [], onResolve, onReadiness, onConfirmImage, onQueueAction, onQuickLook }: WorklistTableProps) {
  return (
    <TableContainer overflowX={{ base: 'auto', desktop: 'hidden' }} maxW="100%">
      <Table variant="clinical" size="sm" layout="fixed" w="100%" minW={{ base: '760px', desktop: '0' }} sx={{ tableLayout: 'fixed', 'tbody td': { py: 2 } }}>
        <Thead><Tr><Th w={{ base: '29%', desktop: '30%' }}>Image</Th><Th w={{ base: '24%', desktop: '23%' }}>Patient / eye</Th><Th w={{ base: '15%', desktop: '15%' }}>Result</Th><Th w={{ base: '18%', desktop: '17%' }}>Review</Th><Th w={{ base: '14%', desktop: '15%' }} isNumeric>Action</Th></Tr></Thead>
        <Tbody>{groups ? groups.map((group) => <PatientGroupRows key={group.key ?? 'unlinked'} group={group} models={models} onResolve={onResolve} onReadiness={onReadiness} onConfirmImage={onConfirmImage} onQueueAction={onQueueAction} onQuickLook={onQuickLook} />) : cases.map((item) => <CaseRow key={item.image_id} item={item} models={models} onResolve={onResolve} onReadiness={onReadiness} onConfirmImage={onConfirmImage} onQueueAction={onQueueAction} onQuickLook={onQuickLook} />)}</Tbody>
      </Table>
    </TableContainer>
  );
}
