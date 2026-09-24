import { useCallback, useRef, useState, type ReactNode } from 'react';
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Button,
  HStack,
  Stack,
  Text,
} from '@chakra-ui/react';

export interface ConfirmDialogOptions {
  title: string;
  body: string[];
  cancelLabel: string;
  confirmLabel: string;
}

interface PendingRequest extends ConfirmDialogOptions {
  resolve: (accepted: boolean) => void;
}

/**
 * One accessible confirmation dialog per page. `ask()` resolves true only when
 * the clinician explicitly accepts; Escape, overlay, and the cancel button all
 * resolve false. The least destructive action receives initial focus.
 */
export function useConfirmDialog(): [ReactNode, (options: ConfirmDialogOptions) => Promise<boolean>] {
  const [pending, setPending] = useState<PendingRequest | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  const ask = useCallback((options: ConfirmDialogOptions) => new Promise<boolean>((resolve) => {
    setPending({ ...options, resolve });
  }), []);

  const finish = (accepted: boolean) => {
    pending?.resolve(accepted);
    setPending(null);
  };

  const dialog = (
    <AlertDialog isOpen={Boolean(pending)} leastDestructiveRef={cancelRef} onClose={() => finish(false)} isCentered>
      <AlertDialogOverlay>
        <AlertDialogContent>
          <AlertDialogHeader fontSize="lg">{pending?.title}</AlertDialogHeader>
          <AlertDialogBody>
            <Stack spacing={2}>
              {pending?.body.map((line) => <Text key={line} fontSize="sm">{line}</Text>)}
            </Stack>
          </AlertDialogBody>
          <AlertDialogFooter>
            <HStack spacing={2}>
              <Button ref={cancelRef} variant="outline" onClick={() => finish(false)}>{pending?.cancelLabel}</Button>
              <Button variant="solid" onClick={() => finish(true)}>{pending?.confirmLabel}</Button>
            </HStack>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogOverlay>
    </AlertDialog>
  );

  return [dialog, ask];
}

export const SWITCH_IMAGE_DIALOG: ConfirmDialogOptions = {
  title: 'Switch to another image?',
  body: [
    'You are still working on this image.',
    'Switching will open a different Worklist case.',
    'Your autosaved draft will be kept. Unconfirmed work will still need your attention.',
  ],
  cancelLabel: 'Stay on this image',
  confirmLabel: 'Switch image',
};

export const LEAVE_CASE_DIALOG: ConfirmDialogOptions = {
  title: 'Leave this image?',
  body: [
    'You are still working on this image.',
    'Your autosaved draft will be kept. Unconfirmed work will still need your attention.',
  ],
  cancelLabel: 'Stay on this image',
  confirmLabel: 'Leave image',
};

export const EDIT_CONFIRMED_GRADE_DIALOG: ConfirmDialogOptions = {
  title: 'Edit confirmed DR grade?',
  body: [
    'This grade has already been confirmed.',
    'Continuing will reopen the grading step and create a new review revision.',
  ],
  cancelLabel: 'Cancel',
  confirmLabel: 'Continue editing',
};

export const EDIT_CONFIRMED_ANNOTATIONS_DIALOG: ConfirmDialogOptions = {
  title: 'Edit confirmed annotations?',
  body: [
    'This annotation set has already been confirmed.',
    'Continuing will reopen annotation review and create a new revision.',
  ],
  cancelLabel: 'Cancel',
  confirmLabel: 'Continue editing',
};
