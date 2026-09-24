import { Button, IconButton, Menu, MenuButton, MenuItem, MenuList } from '@chakra-ui/react';
import { Link } from 'react-router-dom';
import { MoreHorizontal, RotateCcw } from '@/lib/icons';
import type { CaseRecord } from '@/lib/api';
import { imageNeedsAction } from './worklistModel';
import { imageContextConfirmed } from '@/lib/caseProgress';

export function ReviewActionCell({ item, onResolve, onReadiness, onConfirmImage, onQueueAction }: { item: CaseRecord; onResolve: () => void; onReadiness: () => void; onConfirmImage: () => void; onQueueAction: (action: 'EXCLUDE' | 'RESTORE') => void }) {
  const excluded = item.queue_state === 'EXCLUDED';
  const filename = item.filename ?? item.display_name;
  return (
    <Menu placement="bottom-end">
      {!excluded && !imageContextConfirmed(item) ? (
        <Button size="sm" variant="solid" onClick={onConfirmImage}>Confirm Image</Button>
      ) : (
        <Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} size="sm" variant="secondary" isDisabled={excluded} onClick={(event) => { if (excluded) event.preventDefault(); }}>
          {excluded ? 'Excluded' : 'Review'}
        </Button>
      )}
      <MenuButton as={IconButton} aria-label={`More actions for ${filename}`} icon={excluded ? <RotateCcw size={16} /> : <MoreHorizontal size={16} />} size="sm" variant="ghost" title={excluded ? 'Restore to queue' : 'More queue actions'} ml={1} />
      <MenuList>
        {!excluded && imageContextConfirmed(item) && <MenuItem onClick={onConfirmImage}>Confirm Image again</MenuItem>}
        {!excluded && imageNeedsAction(item) && <MenuItem onClick={onReadiness}>Resolve image readiness</MenuItem>}
        {!excluded && <MenuItem onClick={onResolve}>Edit patient / eye</MenuItem>}
        {excluded ? <MenuItem icon={<RotateCcw size={15} />} onClick={() => onQueueAction('RESTORE')}>Restore to queue</MenuItem> : <MenuItem onClick={() => onQueueAction('EXCLUDE')}>Exclude from queue</MenuItem>}
      </MenuList>
    </Menu>
  );
}
