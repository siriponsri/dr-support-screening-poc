/**
 * Sidebar drawer — used on mobile (<768px) where the permanent sidebar is
 * replaced by a left-edge Drawer opened via the toggle in the header.
 */
import {
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerHeader,
  DrawerOverlay,
} from '@chakra-ui/react';
import { Sidebar } from './Sidebar';
import { useSidebarState } from './SidebarStateProvider';

interface SidebarDrawerProps {
  /** Override isOpen/onClose; defaults to the provider state. */
  isOpen?: boolean;
  onClose?: () => void;
}

export function SidebarDrawer(props: SidebarDrawerProps) {
  const state = useSidebarState();
  const isOpen = props.isOpen ?? state.mobileOpen;
  const onClose = props.onClose ?? state.closeMobile;

  return (
    <Drawer isOpen={isOpen} onClose={onClose} placement="left" size="xs">
      <DrawerOverlay />
      <DrawerContent>
        <DrawerCloseButton />
        <DrawerHeader px={4} py={3} fontSize="md">
          Navigation
        </DrawerHeader>
        <DrawerBody p={0}>
          <Sidebar onItemNavigate={onClose} />
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
