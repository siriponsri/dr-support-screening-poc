import { useRef } from 'react';
import { Button, Modal, ModalBody, ModalCloseButton, ModalContent, ModalFooter, ModalHeader, ModalOverlay, Text, useDisclosure } from '@chakra-ui/react';
import { Play } from '@/lib/icons';
import { useT } from '@/lib/i18n';

/** Served from frontend/public/media, so it follows the app's base path (/app/). */
export const JOURNEY_VIDEO_SRC = `${import.meta.env.BASE_URL}media/journey-th.mp4`;
export const JOURNEY_CAPTIONS_SRC = `${import.meta.env.BASE_URL}media/journey-th.vtt`;

/**
 * "Watch how it works" on the sign-in page: a narrated walkthrough with demo data
 * in a closable dialog. Never autoplays; the video pauses whenever the dialog closes.
 */
export function JourneyVideoButton() {
  const t = useT();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const videoRef = useRef<HTMLVideoElement>(null);

  const close = () => {
    videoRef.current?.pause();
    onClose();
  };

  return (
    <>
      <Button type="button" size="lg" w="100%" variant="outline" leftIcon={<Play size={16} aria-hidden="true" />} onClick={onOpen}>
        {t('Watch how it works')}
      </Button>
      <Modal isOpen={isOpen} onClose={close} isCentered size="4xl" closeOnOverlayClick closeOnEsc>
        <ModalOverlay />
        <ModalContent mx={4}>
          <ModalHeader pr={12}>{t('How the Workbench works')}</ModalHeader>
          <ModalCloseButton aria-label={t('Close')} />
          <ModalBody>
            <video ref={videoRef} controls preload="metadata" playsInline src={JOURNEY_VIDEO_SRC}
              style={{ width: '100%', aspectRatio: '16 / 9', background: '#0D1110', borderRadius: '6px' }}>
              <track kind="captions" src={JOURNEY_CAPTIONS_SRC} srcLang="th" label="ไทย" default />
            </video>
            <Text mt={3} fontSize="sm" color="text.secondary">
              {t('A short narrated walkthrough with demo data only. Thai captions are on; use the player to turn them off.')}
            </Text>
          </ModalBody>
          <ModalFooter>
            <Button variant="outline" onClick={close}>{t('Close')}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </>
  );
}
