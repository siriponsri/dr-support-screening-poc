import { Button, IconButton, Menu, MenuButton, MenuItem, MenuList } from '@chakra-ui/react';
import { Link } from 'react-router-dom';
import { MoreHorizontal, RotateCcw } from '@/lib/icons';
import type { CaseRecord } from '@/lib/api';

export function ReviewActionCell({ item, onQueueAction }: { item: CaseRecord; onQueueAction: (action: 'EXCLUDE' | 'RESTORE') => void }) {
  const excluded = item.queue_state === 'EXCLUDED';
  return (
    <Menu placement="bottom-end">
      <Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} size="sm" variant="secondary" isDisabled={excluded} onClick={(event) => { if (excluded) event.preventDefault(); }}>
        {excluded ? 'Excluded' : 'Review'}
      </Button>
      <MenuButton as={IconButton} aria-label={`More actions for ${item.display_name}`} icon={excluded ? <RotateCcw size={16} /> : <MoreHorizontal size={16} />} size="sm" variant="ghost" title={excluded ? 'Restore to queue' : 'More queue actions'} ml={1} />
      <MenuList>
        {excluded ? <MenuItem icon={<RotateCcw size={15} />} onClick={() => onQueueAction('RESTORE')}>Restore to queue</MenuItem> : <MenuItem onClick={() => onQueueAction('EXCLUDE')}>Exclude from queue</MenuItem>}
      </MenuList>
    </Menu>
  );
}
